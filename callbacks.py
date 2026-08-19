"""
Master callbacks file - imports and registers all callback modules
"""

from callbacks_GLOBAL import register_global_callbacks
from callbacks_actuals import register_actuals_callbacks
from callbacks_bsb import register_bsb_callbacks
from callbacks_forecast import register_forecast_callbacks


def register_callbacks(app, data):
    """
    Register all callbacks from modular callback files

    Args:
        app: Dash app instance
        data: Dictionary containing all dataframes (actuals_df, bsb_df, forecast_df, po_df, etc.)
    """
    register_global_callbacks(app, data)
    register_actuals_callbacks(app, data)
    register_bsb_callbacks(app, data)
    register_forecast_callbacks(app, data)
