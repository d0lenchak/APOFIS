import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scipy import stats
from scipy.interpolate import interp1d
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import re

logger = logging.getLogger(__name__)

# Constants
HISTORICAL_WINDOW_QUARTERS = 8  # Use 2 years of historical data for training
DEFAULT_CONFIDENCE_LEVEL = 0.95  # 95% confidence intervals


def parse_quarter_to_date(quarter_str):

    # Convert quarter string (e.g., 'FY26 Q1') to a date object.
    # FY26 Q1 = January 2026 (fiscal year starts in January)
    match = re.match(r'FY(\d{2}) Q(\d)', quarter_str)
    if not match:
        return None
    fy_year = int(match.group(1)) + 2000  # FY26 -> 2026
    quarter = int(match.group(2))

    # Fiscal year starts in January, so FY26 Q1 starts in January 2026
    calendar_year = fy_year

    # Q1=Jan, Q2=Apr, Q3=Jul, Q4=Oct
    month_map = {1: 1, 2: 4, 3: 7, 4: 10}
    month = month_map[quarter]

    return datetime(calendar_year, month, 1)


def date_to_quarter(date_obj):

    # Convert a date object to fiscal quarter string.
    # Fiscal year starts in January: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
    if pd.isna(date_obj):
        return None

    year = date_obj.year
    month = date_obj.month

    # Determine fiscal year and quarter (FY matches calendar year)
    fy = year
    if month <= 3:  # Jan-Mar
        quarter = 1
    elif month <= 6:  # Apr-Jun
        quarter = 2
    elif month <= 9:  # Jul-Sep
        quarter = 3
    else:  # Oct-Dec
        quarter = 4

    return f"FY{fy % 100:02d} Q{quarter}"


def bell_curve_forecast(historical_data, future_quarters, milestone_dates,
                        total_budget, show_confidence=False, **kwargs):
    """
    Generate forecast using Gaussian bell curve with peak at LPFD (Last Patient First Dose).

    Peak spending occurs near LPFD when enrollment is heaviest, with gradual ramp-up
    before and tail-off after enrollment completes.

    Args:
        historical_data (pd.DataFrame): Historical quarters (not used in bell curve)
        future_quarters (list): Quarter strings to forecast (e.g., ['FY26 Q1', 'FY26 Q2'])
        milestone_dates (dict): Keys: FPFD, LPFD (datetime objects)
        total_budget (float): Total BSB budget
        show_confidence (bool): Whether to include ±20% confidence bands
        **kwargs: actuals_spent, open_pos (to calculate remaining budget)

    Returns:
        pd.DataFrame: ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    # Calculate remaining budget after actuals (Open POs are part of future forecast, not a deduction)
    remaining_budget = max(0, total_budget - kwargs.get('actuals_spent', 0))

    # Get LPFD (peak) - if missing, estimate 2 years from FPFD or today
    lpfd = milestone_dates.get('LPFD')
    if pd.isna(lpfd):
        fpfd = milestone_dates.get('FPFD')
        lpfd = (fpfd + timedelta(days=730)) if pd.notna(fpfd) else (datetime.now() + timedelta(days=365))

    # Get FPFD (enrollment start) - if missing, estimate 2 years before LPFD
    fpfd = milestone_dates.get('FPFD')
    if pd.isna(fpfd):
        fpfd = lpfd - timedelta(days=730)

    # Calculate bell curve parameters
    enrollment_duration_days = (lpfd - fpfd).days
    sigma_days = enrollment_duration_days / 4  # 95% of spending within ±2σ (enrollment window)

    # Generate forecast for each quarter using Gaussian PDF centered at LPFD
    forecast_results = []
    for quarter_str in future_quarters:
        quarter_date = parse_quarter_to_date(quarter_str)
        if quarter_date is None:
            continue

        days_from_peak = (quarter_date - lpfd).days  # Distance from LPFD (peak)
        pdf_value = stats.norm.pdf(days_from_peak, loc=0, scale=sigma_days)  # Gaussian probability

        forecast_results.append({'Quarter': quarter_str, 'pdf': pdf_value})

    df_forecast = pd.DataFrame(forecast_results)

    # Normalize PDF so total forecast = remaining budget
    total_pdf = df_forecast['pdf'].sum()
    if total_pdf > 0:
        df_forecast['Forecast'] = (df_forecast['pdf'] / total_pdf) * remaining_budget
    else:
        df_forecast['Forecast'] = remaining_budget / len(future_quarters) if len(future_quarters) > 0 else 0

    # Add confidence intervals (±20% typical study variance)
    if show_confidence:
        df_forecast['Lower_Bound'] = df_forecast['Forecast'] * 0.80
        df_forecast['Upper_Bound'] = df_forecast['Forecast'] * 1.20
    else:
        df_forecast['Lower_Bound'] = df_forecast['Forecast']
        df_forecast['Upper_Bound'] = df_forecast['Forecast']

    return df_forecast[['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']]


def linear_forecast(historical_data, future_quarters, show_confidence=False, **kwargs):
    """
    Generate forecast using linear regression on historical trend.

    Uses the last 8 quarters of historical data to fit a linear trend and extrapolate.

    Args:
        historical_data (pd.DataFrame): Historical quarters with 'Quarter' and 'Amount' columns
        future_quarters (list): List of quarter strings to forecast
        show_confidence (bool): Whether to include confidence intervals
        **kwargs: Additional parameters

    Returns:
        pd.DataFrame: Forecast with columns ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    logger.info("Generating linear forecast...")

    # Use last N quarters for training
    hist_data = historical_data.tail(HISTORICAL_WINDOW_QUARTERS).copy()

    if len(hist_data) < 2:
        logger.warning("Insufficient historical data for linear forecast, using average")
        avg_value = historical_data['Amount'].mean() if len(historical_data) > 0 else 0
        return pd.DataFrame({
            'Quarter': future_quarters,
            'Forecast': [avg_value] * len(future_quarters),
            'Lower_Bound': [avg_value * 0.8] * len(future_quarters),
            'Upper_Bound': [avg_value * 1.2] * len(future_quarters)})

    # Create time index
    hist_data['time_idx'] = range(len(hist_data))

    # Fit linear regression
    X = hist_data['time_idx'].values.reshape(-1, 1)
    y = hist_data['Amount'].values

    # Calculate slope and intercept
    slope, intercept, r_value, p_value, std_err = stats.linregress(X.flatten(), y)

    # Generate forecasts
    forecast_results = []
    for i, quarter_str in enumerate(future_quarters):
        time_idx = len(hist_data) + i
        forecast_value = slope * time_idx + intercept

        # Don't allow negative forecasts
        forecast_value = max(0, forecast_value)

        forecast_results.append({
            'Quarter': quarter_str,
            'Forecast': forecast_value
        })

    df_forecast = pd.DataFrame(forecast_results)

    # Add confidence intervals based on residual standard error
    if show_confidence:
        residuals = y - (slope * X.flatten() + intercept)
        residual_std = np.std(residuals)
        df_forecast['Lower_Bound'] = np.maximum(0, df_forecast['Forecast'] - 1.96 * residual_std)
        df_forecast['Upper_Bound'] = df_forecast['Forecast'] + 1.96 * residual_std
    else:
        df_forecast['Lower_Bound'] = df_forecast['Forecast']
        df_forecast['Upper_Bound'] = df_forecast['Forecast']

    logger.info(f"Linear forecast generated: slope={slope:.2f}, R²={r_value**2:.3f}")

    return df_forecast


def exponential_forecast(historical_data, future_quarters, show_confidence=False, alpha=0.3, **kwargs):
    """
    Generate forecast using exponential smoothing with trend.

    Applies Holt's linear exponential smoothing to capture trend and level.

    Args:
        historical_data (pd.DataFrame): Historical quarters with 'Quarter' and 'Amount' columns
        future_quarters (list): List of quarter strings to forecast
        show_confidence (bool): Whether to include confidence intervals
        alpha (float): Smoothing parameter (0-1), default 0.3
        **kwargs: Additional parameters

    Returns:
        pd.DataFrame: Forecast with columns ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    logger.info(f"Generating exponential smoothing forecast (alpha={alpha})...")

    hist_data = historical_data.tail(HISTORICAL_WINDOW_QUARTERS).copy()

    if len(hist_data) < 2:
        logger.warning("Insufficient historical data for exponential forecast, using average")
        avg_value = historical_data['Amount'].mean() if len(historical_data) > 0 else 0
        return pd.DataFrame({
            'Quarter': future_quarters,
            'Forecast': [avg_value] * len(future_quarters),
            'Lower_Bound': [avg_value * 0.8] * len(future_quarters),
            'Upper_Bound': [avg_value * 1.2] * len(future_quarters)
        })

    # Initialize level and trend
    level = hist_data['Amount'].iloc[0]
    trend = hist_data['Amount'].diff().mean()
    beta = 0.1  # Trend smoothing parameter

    # Apply exponential smoothing
    for value in hist_data['Amount'].values:
        last_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - last_level) + (1 - beta) * trend

    # Forecast future values
    forecast_results = []
    for i, quarter_str in enumerate(future_quarters):
        forecast_value = level + (i + 1) * trend
        forecast_value = max(0, forecast_value)  # No negative forecasts

        forecast_results.append({
            'Quarter': quarter_str,
            'Forecast': forecast_value
        })

    df_forecast = pd.DataFrame(forecast_results)

    # Add confidence intervals
    if show_confidence:
        # Confidence grows with forecast horizon
        for i in range(len(df_forecast)):
            uncertainty = df_forecast.loc[i, 'Forecast'] * 0.15 * (1 + i * 0.1)
            df_forecast.loc[i, 'Lower_Bound'] = max(0, df_forecast.loc[i, 'Forecast'] - uncertainty)
            df_forecast.loc[i, 'Upper_Bound'] = df_forecast.loc[i, 'Forecast'] + uncertainty
    else:
        df_forecast['Lower_Bound'] = df_forecast['Forecast']
        df_forecast['Upper_Bound'] = df_forecast['Forecast']

    logger.info(f"Exponential forecast generated: level={level:.0f}, trend={trend:.0f}")

    return df_forecast


def polynomial_forecast(historical_data, future_quarters, show_confidence=False, degree=2, **kwargs):
    """
    Generate forecast using polynomial regression.

    Fits a polynomial curve to historical data and extrapolates. Good for capturing
    non-linear trends (growth/decline curves).

    Args:
        historical_data (pd.DataFrame): Historical quarters with 'Quarter' and 'Amount' columns
        future_quarters (list): List of quarter strings to forecast
        show_confidence (bool): Whether to include confidence intervals
        degree (int): Polynomial degree (2 or 3 recommended)
        **kwargs: Additional parameters

    Returns:
        pd.DataFrame: Forecast with columns ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    logger.info(f"Generating polynomial forecast (degree={degree})...")

    hist_data = historical_data.tail(HISTORICAL_WINDOW_QUARTERS).copy()

    if len(hist_data) < degree + 1:
        logger.warning(f"Insufficient data for degree-{degree} polynomial, using linear")
        return linear_forecast(historical_data, future_quarters, show_confidence, **kwargs)

    # Create time index
    hist_data['time_idx'] = range(len(hist_data))

    # Fit polynomial
    X = hist_data['time_idx'].values
    y = hist_data['Amount'].values

    coefficients = np.polyfit(X, y, degree)
    poly_func = np.poly1d(coefficients)

    # Generate forecasts
    forecast_results = []
    for i, quarter_str in enumerate(future_quarters):
        time_idx = len(hist_data) + i
        forecast_value = poly_func(time_idx)
        forecast_value = max(0, forecast_value)  # No negative forecasts

        forecast_results.append({
            'Quarter': quarter_str,
            'Forecast': forecast_value
        })

    df_forecast = pd.DataFrame(forecast_results)

    # Add confidence intervals based on residuals
    if show_confidence:
        y_pred = poly_func(X)
        residuals = y - y_pred
        residual_std = np.std(residuals)
        df_forecast['Lower_Bound'] = np.maximum(0, df_forecast['Forecast'] - 1.96 * residual_std)
        df_forecast['Upper_Bound'] = df_forecast['Forecast'] + 1.96 * residual_std
    else:
        df_forecast['Lower_Bound'] = df_forecast['Forecast']
        df_forecast['Upper_Bound'] = df_forecast['Forecast']

    logger.info(f"Polynomial forecast generated: coefficients={coefficients}")

    return df_forecast


def monte_carlo_forecast(historical_data, future_quarters, show_confidence=True, n_simulations=1000, **kwargs):
    """
    Generate forecast using Monte Carlo simulation.

    Runs multiple simulations with randomized parameters to generate a distribution
    of possible outcomes. Provides realistic confidence intervals.

    Args:
        historical_data (pd.DataFrame): Historical quarters with 'Quarter' and 'Amount' columns
        future_quarters (list): List of quarter strings to forecast
        show_confidence (bool): Whether to include confidence intervals (always True for Monte Carlo)
        n_simulations (int): Number of simulation runs
        **kwargs: Additional parameters

    Returns:
        pd.DataFrame: Forecast with columns ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    logger.info(f"Generating Monte Carlo forecast ({n_simulations} simulations)...")

    hist_data = historical_data.tail(HISTORICAL_WINDOW_QUARTERS).copy()

    if len(hist_data) < 3:
        logger.warning("Insufficient data for Monte Carlo, using average with wide bounds")
        avg_value = historical_data['Amount'].mean() if len(historical_data) > 0 else 0
        return pd.DataFrame({
            'Quarter': future_quarters,
            'Forecast': [avg_value] * len(future_quarters),
            'Lower_Bound': [avg_value * 0.5] * len(future_quarters),
            'Upper_Bound': [avg_value * 1.5] * len(future_quarters)
        })

    # Calculate historical mean, trend, and volatility
    mean_value = hist_data['Amount'].mean()
    trend = hist_data['Amount'].diff().mean()
    volatility = hist_data['Amount'].std()

    # Run simulations
    simulation_results = []

    for sim in range(n_simulations):
        sim_forecast = []
        current_value = hist_data['Amount'].iloc[-1]

        for i in range(len(future_quarters)):
            # Random walk with drift
            random_shock = np.random.normal(0, volatility)
            current_value = current_value + trend + random_shock
            current_value = max(0, current_value)  # No negative values
            sim_forecast.append(current_value)

        simulation_results.append(sim_forecast)

    # Calculate statistics across simulations
    simulation_array = np.array(simulation_results)

    forecast_results = []
    for i, quarter_str in enumerate(future_quarters):
        forecast_results.append({
            'Quarter': quarter_str,
            'Forecast': np.median(simulation_array[:, i]),
            'Lower_Bound': np.percentile(simulation_array[:, i], 2.5),
            'Upper_Bound': np.percentile(simulation_array[:, i], 97.5)
        })

    df_forecast = pd.DataFrame(forecast_results)

    logger.info(f"Monte Carlo forecast generated: mean={df_forecast['Forecast'].mean():.0f}")

    return df_forecast


def tree_forecast(historical_data, future_quarters, show_confidence=False, n_estimators=100, **kwargs):
    """
    Generate forecast using Random Forest regression.

    Uses ensemble of decision trees to capture complex patterns in historical data.
    Good for non-linear relationships but requires substantial historical data.

    Args:
        historical_data (pd.DataFrame): Historical quarters with 'Quarter' and 'Amount' columns
        future_quarters (list): List of quarter strings to forecast
        show_confidence (bool): Whether to include confidence intervals
        n_estimators (int): Number of trees in the forest
        **kwargs: Additional parameters

    Returns:
        pd.DataFrame: Forecast with columns ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    logger.info(f"Generating Random Forest forecast ({n_estimators} trees)...")

    hist_data = historical_data.tail(HISTORICAL_WINDOW_QUARTERS * 2).copy()  # Need more data for RF

    if len(hist_data) < 6:
        logger.warning("Insufficient data for Random Forest, falling back to linear")
        return linear_forecast(historical_data, future_quarters, show_confidence, **kwargs)

    # Create features: time index, lagged values, moving averages
    hist_data['time_idx'] = range(len(hist_data))
    hist_data['lag_1'] = hist_data['Amount'].shift(1)
    hist_data['lag_2'] = hist_data['Amount'].shift(2)
    hist_data['ma_3'] = hist_data['Amount'].rolling(window=3).mean()

    # Drop rows with NaN from lagging/rolling
    hist_data = hist_data.dropna()

    if len(hist_data) < 4:
        return linear_forecast(historical_data, future_quarters, show_confidence, **kwargs)

    # Prepare training data
    feature_cols = ['time_idx', 'lag_1', 'lag_2', 'ma_3']
    X = hist_data[feature_cols].values
    y = hist_data['Amount'].values

    # Train Random Forest
    rf = RandomForestRegressor(n_estimators=n_estimators, random_state=42)
    rf.fit(X, y)

    # Generate forecasts
    forecast_results = []
    last_values = hist_data['Amount'].tail(3).values

    for i, quarter_str in enumerate(future_quarters):
        time_idx = len(hist_data) + i
        lag_1 = last_values[-1] if len(last_values) >= 1 else hist_data['Amount'].mean()
        lag_2 = last_values[-2] if len(last_values) >= 2 else hist_data['Amount'].mean()
        ma_3 = np.mean(last_values[-3:]) if len(last_values) >= 3 else hist_data['Amount'].mean()

        X_pred = np.array([[time_idx, lag_1, lag_2, ma_3]])
        forecast_value = rf.predict(X_pred)[0]
        forecast_value = max(0, forecast_value)

        forecast_results.append({
            'Quarter': quarter_str,
            'Forecast': forecast_value
        })

        # Update last_values for next iteration
        last_values = np.append(last_values[1:], forecast_value)

    df_forecast = pd.DataFrame(forecast_results)

    # Confidence intervals based on tree predictions variance
    if show_confidence:
        # For each forecast point, get all tree predictions
        for i in range(len(df_forecast)):
            time_idx = len(hist_data) + i
            lag_1 = forecast_results[max(0, i-1)]['Forecast'] if i > 0 else hist_data['Amount'].iloc[-1]
            lag_2 = forecast_results[max(0, i-2)]['Forecast'] if i > 1 else hist_data['Amount'].iloc[-2]
            ma_3 = np.mean([r['Forecast'] for r in forecast_results[max(0, i-2):i+1]]) if i > 0 else hist_data['Amount'].mean()

            X_pred = np.array([[time_idx, lag_1, lag_2, ma_3]])
            tree_predictions = [tree.predict(X_pred)[0] for tree in rf.estimators_]

            df_forecast.loc[i, 'Lower_Bound'] = max(0, np.percentile(tree_predictions, 2.5))
            df_forecast.loc[i, 'Upper_Bound'] = np.percentile(tree_predictions, 97.5)
    else:
        df_forecast['Lower_Bound'] = df_forecast['Forecast']
        df_forecast['Upper_Bound'] = df_forecast['Forecast']

    logger.info(f"Random Forest forecast generated: feature importance={rf.feature_importances_}")

    return df_forecast


def generate_flat_forecast(total_budget, future_quarters):
    """
    Generate flat (evenly distributed) forecast for accounts like A80020 - Investigator Grants.

    These accounts typically have steady, predictable spend patterns regardless of enrollment curve.

    Args:
        total_budget (float): Total budget to distribute
        future_quarters (list): List of quarter strings to forecast

    Returns:
        pd.DataFrame: Forecast with columns ['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']
    """
    logger.info(f"Generating flat forecast for {len(future_quarters)} quarters")

    quarterly_amount = total_budget / len(future_quarters) if len(future_quarters) > 0 else 0

    df_forecast = pd.DataFrame({
        'Quarter': future_quarters,
        'Forecast': [quarterly_amount] * len(future_quarters),
        'Lower_Bound': [quarterly_amount * 0.9] * len(future_quarters),  # ±10% variation
        'Upper_Bound': [quarterly_amount * 1.1] * len(future_quarters)
    })

    return df_forecast


def quarterly_to_monthly(quarterly_df, start_year=None, start_quarter=None):
    """
    Convert quarterly forecast data to monthly breakdown.

    Divides each quarter evenly into 3 months. This is a simple but effective
    approach for users who want monthly granularity for budgeting/Excel exports.

    Args:
        quarterly_df (pd.DataFrame): DataFrame with 'Quarter' and 'Forecast' columns
                                     Quarter format: 'FY26 Q1', 'FY26 Q2', etc.
        start_year (int): Starting fiscal year (e.g., 2026). If None, extracted from first quarter
        start_quarter (int): Starting quarter (1-4). If None, extracted from first quarter

    Returns:
        pd.DataFrame: Columns ['Month', 'Forecast'] where Month is 'Jan 2026', 'Feb 2026', etc.
    """
    import re
    from datetime import datetime

    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    monthly_data = []

    for _, row in quarterly_df.iterrows():
        quarter_str = row['Quarter']
        forecast_value = row['Forecast']

        # Parse quarter string: 'FY26 Q1' -> year=26, quarter=1
        match = re.match(r'FY(\d{2}) Q(\d)', quarter_str)
        if not match:
            logger.warning(f"Could not parse quarter: {quarter_str}")
            continue

        fy_year = int(match.group(1)) + 2000  # FY26 -> 2026
        quarter = int(match.group(2))

        # Determine which months belong to this quarter
        # Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
        quarter_months = {
            1: [1, 2, 3],      # Jan, Feb, Mar
            2: [4, 5, 6],      # Apr, May, Jun
            3: [7, 8, 9],      # Jul, Aug, Sep
            4: [10, 11, 12]    # Oct, Nov, Dec
        }

        months = quarter_months.get(quarter, [])
        monthly_amount = forecast_value / 3  # Divide quarterly amount evenly

        for month_num in months:
            month_name = month_names[month_num - 1]
            month_label = f"{month_name} {fy_year}"
            monthly_data.append({
                'Month': month_label,
                'Year': fy_year,
                'Month_Num': month_num,
                'Forecast': monthly_amount
            })

    df_monthly = pd.DataFrame(monthly_data)

    # Sort by year and month
    if len(df_monthly) > 0:
        df_monthly = df_monthly.sort_values(['Year', 'Month_Num']).reset_index(drop=True)

    return df_monthly


if __name__ == "__main__":
    # Test forecasting functions
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Create sample historical data
    quarters = ['FY24 Q1', 'FY24 Q2', 'FY24 Q3', 'FY24 Q4',
                'FY25 Q1', 'FY25 Q2', 'FY25 Q3', 'FY25 Q4']
    amounts = [100000, 150000, 200000, 250000, 300000, 350000, 400000, 450000]

    hist_data = pd.DataFrame({'Quarter': quarters, 'Amount': amounts})
    future_qtrs = ['FY26 Q1', 'FY26 Q2', 'FY26 Q3', 'FY26 Q4']

    # Test bell curve
    milestones = {
        'FPFD': datetime(2024, 1, 1),
        'LPFD': datetime(2025, 12, 31),
        'LPLV': datetime(2026, 6, 30),
        'DBL': datetime(2026, 9, 30)
    }

    bell_result = bell_curve_forecast(hist_data, future_qtrs, milestones, 2000000, show_confidence=True)
    print("\nBell Curve Forecast:")
    print(bell_result)

    # Test linear
    linear_result = linear_forecast(hist_data, future_qtrs, show_confidence=True)
    print("\nLinear Forecast:")
    print(linear_result)


def context_aware_forecast(historical_data, future_quarters, milestone_dates, total_budget,
                          show_confidence=False, context_data=None, **kwargs):
    """
    Generate forecast using historical spending patterns from similar studies.

    This enhanced method learns from completed/ongoing studies with similar characteristics:
    - CDU (Clinical Development Unit)
    - Therapeutic Area
    - Study phase/milestones achieved

    It identifies spending patterns between milestones and applies them to the forecast.

    Args:
        historical_data (pd.DataFrame): Historical quarters for current study
        future_quarters (list): Quarters to forecast
        milestone_dates (dict): FPFV, FPFD, LPFD, LPLV, DBL dates
        total_budget (float): Total budget to distribute
        show_confidence (bool): Include confidence intervals
        context_data (dict): Dictionary containing:
            - 'all_actuals_df': Full actuals dataframe with all studies
            - 'study_daily_df': Study metadata (CDU, TA, Indication)
            - 'current_study_id': Current study being forecast
            - 'current_cdu': CDU for current study
            - 'current_ta': Therapeutic area for current study
        **kwargs: actuals_spent, open_pos

    Returns:
        pd.DataFrame: Context-aware forecast
    """
    logger.info("Generating context-aware forecast using similar study patterns...")

    # Get remaining budget (Open POs are part of future forecast, not a deduction)
    actuals_spent = kwargs.get('actuals_spent', 0)
    remaining_budget = max(0, total_budget - actuals_spent)

    # If no context data provided, fall back to bell curve
    if context_data is None or not all(k in context_data for k in ['all_actuals_df', 'current_cdu']):
        logger.warning("No context data provided, falling back to bell curve forecast")
        return bell_curve_forecast(historical_data, future_quarters, milestone_dates,
                                   total_budget, show_confidence, **kwargs)

    all_actuals = context_data['all_actuals_df']
    study_daily = context_data.get('study_daily_df')
    current_study = context_data.get('current_study_id')
    current_cdu = context_data.get('current_cdu')
    current_ta = context_data.get('current_ta')

    # Extract milestone info for current study
    fpfv = milestone_dates.get('FPFV')
    fpfd = milestone_dates.get('FPFD')
    lpfd = milestone_dates.get('LPFD')
    lplv = milestone_dates.get('LPLV')
    dbl = milestone_dates.get('DBL')

    # Identify which milestone phase we're in/approaching
    today = datetime.now()
    milestone_phases = []

    if fpfd and pd.notna(fpfd):
        if today < fpfd:
            milestone_phases.append(('pre_fpfd', None, fpfd))
        if lpfd and pd.notna(lpfd):
            if fpfd <= today < lpfd:
                milestone_phases.append(('enrollment', fpfd, lpfd))
            elif today < fpfd:
                milestone_phases.append(('enrollment', fpfd, lpfd))

    if lpfd and lplv and pd.notna(lpfd) and pd.notna(lplv):
        if lpfd <= today < lplv:
            milestone_phases.append(('followup', lpfd, lplv))
        elif today < lpfd:
            milestone_phases.append(('followup', lpfd, lplv))

    if lplv and dbl and pd.notna(lplv) and pd.notna(dbl):
        if lplv <= today < dbl:
            milestone_phases.append(('closeout', lplv, dbl))
        elif today < lplv:
            milestone_phases.append(('closeout', lplv, dbl))

    # Find similar studies in the database
    similar_studies = []

    if study_daily is not None and not study_daily.empty:
        # Find studies with same CDU (primary match)
        cdu_matches = study_daily[study_daily['CDU'] == current_cdu]['Study_Number_Short'].tolist()

        # Find studies with same TA (secondary match)
        ta_matches = []
        if current_ta and pd.notna(current_ta):
            ta_matches = study_daily[study_daily['Therapeutic_Area'] == current_ta]['Study_Number_Short'].tolist()

        # Prioritize CDU matches, then TA matches
        similar_studies = cdu_matches if cdu_matches else ta_matches

        logger.info(f"Found {len(similar_studies)} similar studies (CDU={current_cdu}, TA={current_ta})")

    # Calculate spending patterns from similar studies
    phase_patterns = {}

    if similar_studies and len(similar_studies) > 0:
        # For each phase, calculate average spending intensity
        for phase_name, start_date, end_date in milestone_phases:
            if not start_date or not end_date:
                continue

            phase_spending = []

            # Look at similar studies' spending during equivalent phases
            for study_short in similar_studies[:10]:  # Limit to top 10 similar
                # Match study short to full study ID in actuals
                study_pattern = f'-{study_short}'
                study_actuals = all_actuals[all_actuals['Study_ID'].str.contains(study_pattern, na=False)]

                if len(study_actuals) > 0:
                    # Get quarterly spending and calculate intensity
                    quarter_cols = [col for col in study_actuals.columns if 'Q' in col and 'FY' in col]
                    total_spend = study_actuals[quarter_cols].sum().sum()

                    if total_spend > 0:
                        phase_spending.append(total_spend / len(quarter_cols) if len(quarter_cols) > 0 else 0)

            if len(phase_spending) > 0:
                avg_intensity = np.mean(phase_spending)
                phase_patterns[phase_name] = avg_intensity
                logger.info(f"Phase '{phase_name}': avg intensity ${avg_intensity:,.0f}/quarter from {len(phase_spending)} similar studies")

    # If we couldn't learn patterns, use bell curve as baseline
    if not phase_patterns:
        logger.warning("Could not extract patterns from similar studies, using bell curve")
        return bell_curve_forecast(historical_data, future_quarters, milestone_dates,
                                   total_budget, show_confidence, **kwargs)

    # Generate forecast by applying learned patterns
    forecast_results = []

    for quarter_str in future_quarters:
        quarter_date = parse_quarter_to_date(quarter_str)
        if not quarter_date:
            continue

        # Determine which phase this quarter falls into
        quarter_amount = 0

        for phase_name, start_date, end_date in milestone_phases:
            if start_date and end_date and pd.notna(start_date) and pd.notna(end_date):
                if start_date <= quarter_date <= end_date:
                    # Use learned pattern for this phase
                    if phase_name in phase_patterns:
                        quarter_amount = phase_patterns[phase_name]
                    break

        forecast_results.append({
            'Quarter': quarter_str,
            'Forecast': quarter_amount
        })

    df_forecast = pd.DataFrame(forecast_results)

    # Normalize to remaining budget
    total_forecast = df_forecast['Forecast'].sum()
    if total_forecast > 0:
        df_forecast['Forecast'] = (df_forecast['Forecast'] / total_forecast) * remaining_budget
    else:
        df_forecast['Forecast'] = remaining_budget / len(future_quarters) if len(future_quarters) > 0 else 0

    # Add confidence intervals
    if show_confidence:
        # Wider confidence for context-aware (more uncertainty in pattern matching)
        df_forecast['Lower_Bound'] = df_forecast['Forecast'] * 0.70
        df_forecast['Upper_Bound'] = df_forecast['Forecast'] * 1.30
    else:
        df_forecast['Lower_Bound'] = df_forecast['Forecast']
        df_forecast['Upper_Bound'] = df_forecast['Forecast']

    logger.info(f"Context-aware forecast generated: total=${df_forecast['Forecast'].sum():,.0f}")

    return df_forecast[['Quarter', 'Forecast', 'Lower_Bound', 'Upper_Bound']]


def get_normalized_spending_pattern(context_data, milestone_dates, future_quarters):
    """
    Extract generalized spending pattern across milestone phases using REAL actuals data.

    Analyzes actual spending across 6 milestone tranches:
    1. Startup (Pre-FPFV)
    2. Lead-in (FPFV to FPFD)
    3. Active Enrollment (FPFD to LPFD)
    4. Ramp Down (LPFD to LPLV)
    5. Close-out (LPLV to DBL)
    6. Read-out (Post DBL)

    Args:
        context_data (dict): Contains all_actuals_df, study_daily_df
        milestone_dates (dict): Current study milestones
        future_quarters (list): Quarters to forecast

    Returns:
        dict: {
            'pattern_x': list of quarters,
            'pattern_y': list of normalized spending showing phase-based peaks/valleys,
            'confidence_upper': upper bound,
            'confidence_lower': lower bound
        }
    """

    if not context_data:
        return None

    all_actuals = context_data.get('all_actuals_df')
    study_daily = context_data.get('study_daily_df')

    if all_actuals is None or study_daily is None:
        return None

    # Phase spending aggregator: {phase: [list of normalized spending values]}
    phase_spending = {
        'startup': [],
        'lead_in': [],
        'active_enrollment': [],
        'ramp_down': [],
        'close_out': [],
        'read_out': []
    }

    # Find studies with milestone data and actual spending
    studies_analyzed = 0

    for _, study_row in study_daily.iterrows():
        study_short = study_row.get('Study_Number_Short')
        if pd.isna(study_short):
            continue

        # Get milestone dates for this study
        study_fpfv = pd.to_datetime(study_row.get('FPFV'), errors='coerce')
        study_fpfd = pd.to_datetime(study_row.get('FPFD'), errors='coerce')
        study_lpfd = pd.to_datetime(study_row.get('LPFD'), errors='coerce')
        study_lplv = pd.to_datetime(study_row.get('LPLV'), errors='coerce')
        study_dbl = pd.to_datetime(study_row.get('DBL'), errors='coerce')

        # Only use studies with at least some milestone data
        if pd.isna(study_fpfv) and pd.isna(study_fpfd):
            continue

        # Get actuals data for this study
        study_pattern = f'-{study_short}'
        study_actuals = all_actuals[all_actuals['Study_ID'].str.contains(study_pattern, na=False)]

        if len(study_actuals) == 0:
            continue

        # Get quarterly columns with data
        quarter_cols = [col for col in study_actuals.columns if 'Q' in col and 'FY' in col]
        quarter_cols = sorted(quarter_cols)

        # Collect spending by quarter with phase assignment
        for qtr in quarter_cols:
            qtr_amount = study_actuals[qtr].sum()
            if qtr_amount == 0:
                continue

            # Convert quarter to date for phase matching
            qtr_date = parse_quarter_to_date(qtr)
            if qtr_date is None:
                continue

            # Determine which phase this quarter belongs to
            phase = None
            if pd.notna(study_dbl) and qtr_date >= study_dbl:
                phase = 'read_out'
            elif pd.notna(study_lplv) and pd.notna(study_dbl) and study_lplv <= qtr_date < study_dbl:
                phase = 'close_out'
            elif pd.notna(study_lpfd) and pd.notna(study_lplv) and study_lpfd <= qtr_date < study_lplv:
                phase = 'ramp_down'
            elif pd.notna(study_fpfd) and pd.notna(study_lpfd) and study_fpfd <= qtr_date < study_lpfd:
                phase = 'active_enrollment'
            elif pd.notna(study_fpfv) and pd.notna(study_fpfd) and study_fpfv <= qtr_date < study_fpfd:
                phase = 'lead_in'
            elif pd.notna(study_fpfv) and qtr_date < study_fpfv:
                phase = 'startup'
            elif pd.notna(study_fpfd) and qtr_date < study_fpfd:
                # If no FPFV but have FPFD, assume this is startup
                phase = 'startup'

            if phase:
                phase_spending[phase].append(qtr_amount)

        studies_analyzed += 1

    if studies_analyzed == 0:
        logger.warning("No studies with milestone data and actuals found for pattern extraction")
        return None

    logger.info(f"Analyzed {studies_analyzed} studies with milestone-mapped actuals")

    # Calculate average spending intensity per phase (normalized)
    phase_means = {}
    for phase, amounts in phase_spending.items():
        if len(amounts) > 0:
            # Calculate mean spend per quarter in this phase
            phase_means[phase] = np.mean(amounts)
            logger.info(f"  {phase}: {len(amounts)} quarters, avg ${phase_means[phase]:,.0f}")
        else:
            phase_means[phase] = 0

    # Normalize phase means to show relative intensity (0-1 scale)
    max_phase_mean = max(phase_means.values()) if phase_means else 1
    if max_phase_mean == 0:
        max_phase_mean = 1

    normalized_phase_intensity = {
        phase: mean / max_phase_mean for phase, mean in phase_means.items()
    }

    # Map current study milestones to forecast quarters
    current_fpfv = milestone_dates.get('FPFV')
    current_fpfd = milestone_dates.get('FPFD')
    current_lpfd = milestone_dates.get('LPFD')
    current_lplv = milestone_dates.get('LPLV')
    current_dbl = milestone_dates.get('DBL')

    # Build pattern for forecast quarters based on phases
    pattern_y = []
    for qtr in future_quarters:
        qtr_date = parse_quarter_to_date(qtr)
        if qtr_date is None:
            pattern_y.append(0.5)  # Default mid-level
            continue

        # Determine phase for this forecast quarter
        intensity = 0.5  # Default
        if current_dbl and pd.notna(current_dbl) and qtr_date >= current_dbl:
            intensity = normalized_phase_intensity['read_out']
        elif current_lplv and pd.notna(current_lplv) and current_dbl and pd.notna(current_dbl) and current_lplv <= qtr_date < current_dbl:
            intensity = normalized_phase_intensity['close_out']
        elif current_lpfd and pd.notna(current_lpfd) and current_lplv and pd.notna(current_lplv) and current_lpfd <= qtr_date < current_lplv:
            intensity = normalized_phase_intensity['ramp_down']
        elif current_fpfd and pd.notna(current_fpfd) and current_lpfd and pd.notna(current_lpfd) and current_fpfd <= qtr_date < current_lpfd:
            intensity = normalized_phase_intensity['active_enrollment']
        elif current_fpfv and pd.notna(current_fpfv) and current_fpfd and pd.notna(current_fpfd) and current_fpfv <= qtr_date < current_fpfd:
            intensity = normalized_phase_intensity['lead_in']
        elif current_fpfv and pd.notna(current_fpfv) and qtr_date < current_fpfv:
            intensity = normalized_phase_intensity['startup']
        elif current_fpfd and pd.notna(current_fpfd) and qtr_date < current_fpfd:
            intensity = normalized_phase_intensity['startup']

        pattern_y.append(intensity)

    # Create confidence bounds (±20% of phase intensity)
    upper_bound = [min(1.0, y * 1.2) for y in pattern_y]
    lower_bound = [max(0.0, y * 0.8) for y in pattern_y]

    logger.info(f"Phase-based pattern generated: {len(pattern_y)} quarters across {studies_analyzed} studies")

    return {
        'pattern_x': future_quarters,
        'pattern_y': pattern_y,
        'confidence_upper': upper_bound,
        'confidence_lower': lower_bound
    }
