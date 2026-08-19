import logging
import re
import pandas as pd
import numpy as np
from datetime import datetime
from dash import Output, Input, State, html, no_update
import plotly.graph_objects as go
from dash import dash_table

from config import COLORS, get_colors, BASE_DIR, is_program_finance_account
from data_loader import get_display_name, is_actual_study, get_study_phase

logger = logging.getLogger(__name__)


def register_forecast_callbacks(app, data):
    """Register callbacks for Forecast tab."""
    core_df = data['core_df']
    forecast_df = data['forecast_df']
    map_df = data['map_df']
    bsb_df = data['bsb_df']
    po_df = data['po_df']
    study_daily_df = data['study_daily_df']
    quarter_cols = data['quarter_cols']
    forecast_quarter_cols = data['forecast_quarter_cols']

    logger.info("Registering forecast callbacks...")

    # ==================== HELPER FUNCTIONS ====================

    def expand_phase_groups(study_ids, selected_pcodes):
        """Expand phase group selections (PHASE_*) to individual study IDs."""
        if 'ALL' in study_ids:
            return study_ids

        expanded_study_ids = []
        for study_id in study_ids:
            if study_id.startswith('PHASE_'):
                # Extract phase from PHASE_PHASE_1 -> "Phase 1", PHASE_OTHER -> "Other"
                # Split only once to handle "PHASE_" prefix
                phase_part = study_id.split('PHASE_', 1)[1] if 'PHASE_' in study_id else study_id
                # Handle "OTHER" -> "Other", "PHASE_1" -> "Phase 1"
                if phase_part == 'OTHER':
                    phase_key = 'Other'
                else:
                    phase_key = phase_part.replace('_', ' ').title()
                # Get all studies matching this phase
                all_studies = core_df[core_df['P_Code'].isin(selected_pcodes)]['Study_ID'].dropna().unique()
                for study in all_studies:
                    if get_study_phase(study, study_daily_df) == phase_key:
                        expanded_study_ids.append(study)
            else:
                expanded_study_ids.append(study_id)

        return expanded_study_ids

    # ==================== FORECAST PAGE CALLBACKS ====================

    @app.callback(
        [Output('forecast-study-dropdown', 'options'),
         Output('forecast-study-dropdown', 'value')],
        Input('forecast-project-dropdown', 'value'),
        State('forecast-study-dropdown', 'value')
    )
    def update_forecast_studies(project_codes, current_value):
        """Update forecast page study dropdown with phase buckets."""
        if not project_codes or len(project_codes) == 0:
            return [{'label': 'Select a Program first...', 'value': 'NONE'}], []

        # Get list of P_Codes from selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

        # Get ALL studies for selected programs (including placeholders)
        studies = core_df[core_df['P_Code'].isin(selected_pcodes)]['Study_ID'].dropna().unique()
        studies = sorted([s for s in studies if s])

        if len(studies) == 0:
            return [{'label': 'No studies found', 'value': 'NONE'}], []

        # Organize studies by phase buckets
        phase_buckets = {
            'Phase 1': [],
            'Phase 2': [],
            'Phase 3': [],
            'Phase 4': [],
            'Other': []}

        for study in studies:
            # Get P_Code for this study to enable REGN# matching
            study_pcode = core_df[core_df['Study_ID'] == study]['P_Code'].iloc[0] if len(core_df[core_df['Study_ID'] == study]) > 0 else None
            phase = get_study_phase(study, study_daily_df, pcode=study_pcode, map_df=map_df)
            display_name = get_display_name(study, study_daily_df, pcode=study_pcode, map_df=map_df)
            phase_buckets[phase].append((display_name, study))

        # dropdown buckets
        options = [{'label': 'ALL STUDIES', 'value': 'ALL'}]
        phase_order = ['Phase 1', 'Phase 2', 'Phase 3', 'Phase 4', 'Other']

        for phase in phase_order:
            if len(phase_buckets[phase]) > 0:
                # Add phase bucket group selector
                options.append({
                    'label': f'{phase} (All) ----------',
                    'value': f'PHASE_{phase.replace(" ", "_").upper()}'
                })
                # Add individual studies in this phase
                for display_name, study_value in sorted(phase_buckets[phase]):
                    options.append({
                        'label': f'    {display_name}',
                        'value': study_value
                    })

        # Set default to 'ALL' if no current value, otherwise preserve it
        if not current_value or len(current_value) == 0:
            return options, ['ALL']
        return options, no_update

    @app.callback(
        [Output('forecast-account-dropdown', 'options'),
         Output('forecast-account-dropdown', 'value')],
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value')],
        State('forecast-account-dropdown', 'value')
    )
    def update_forecast_accounts(project_codes, study_ids, current_value):
        """Update forecast page account dropdown."""
        if not project_codes or len(project_codes) == 0:
            return [{'label': 'Select a Program first...', 'value': 'NONE'}], []
        if not study_ids or len(study_ids) == 0:
            return [{'label': 'Select a Study first...', 'value': 'NONE'}], []

        # Get list of P_Codes from selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

        if 'ALL' in study_ids:
            filtered = core_df[core_df['P_Code'].isin(selected_pcodes)]
        else:
            expanded_study_ids = expand_phase_groups(study_ids, selected_pcodes)
            filtered = core_df[(core_df['P_Code'].isin(selected_pcodes)) & (core_df['Study_ID'].isin(expanded_study_ids))]

        accounts = filtered['Account_Clean'].dropna().unique()
        accounts = sorted([a for a in accounts if a])

        if len(accounts) == 0:
            return [{'label': 'No accounts found', 'value': 'NONE'}], []

        pf_accounts = [acc for acc in accounts if is_program_finance_account(acc)]
        other_accounts = [acc for acc in accounts if not is_program_finance_account(acc)]

        options = [{'label': '✓ All Accounts', 'value': 'ALL'}]

        if len(pf_accounts) > 0:
            options.append({'label': '📁 Program Finance (All)', 'value': 'PF_GROUP'})
            for acc in pf_accounts:
                options.append({'label': f'    • {acc}', 'value': acc})

        if len(other_accounts) > 0:
            options.append({'label': '─────────', 'value': 'DIVIDER', 'disabled': True})
            for acc in other_accounts:
                options.append({'label': acc, 'value': acc})

        # Set default to 'PF_GROUP' if no current value, otherwise preserve it
        if not current_value or len(current_value) == 0:
            return options, ['PF_GROUP']
        return options, no_update

    # UPDATE THERAPEUTIC AREA ON SELECTION =======================
    @app.callback(
        [Output('forecast-ta-dropdown', 'options'),
         Output('forecast-ta-dropdown', 'value')],
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value')],
        State('forecast-ta-dropdown', 'value'))

    def update_forecast_tas(project_codes, study_ids, current_value):
        if not project_codes or len(project_codes) == 0:
            return [{'label': 'Select a Program first...', 'value': 'NONE'}], []
        if not study_ids or len(study_ids) == 0:
            return [{'label': 'Select a Study first...', 'value': 'NONE'}], []

        # Get selected P_Codes
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

        # Expand phase group selections
        expanded_study_ids = expand_phase_groups(study_ids, selected_pcodes)

        # Filter studies
        if 'ALL' in study_ids:
            filtered_studies = core_df[core_df['P_Code'].isin(selected_pcodes)]['Study_ID'].dropna().unique()
        else:
            filtered_studies = expanded_study_ids

        # Extract TAs from study_daily_df
        tas = set()
        for study_id in filtered_studies:
            match = re.match(r'\d{4}-(\d{3,4})$', str(study_id))
            if match:
                study_short = match.group(1)
                matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                if not matching_row.empty and pd.notna(matching_row.iloc[0]['Therapeutic_Area']):
                    tas.add(matching_row.iloc[0]['Therapeutic_Area'])

        tas = sorted(list(tas))

        if len(tas) == 0:
            return [{'label': 'No therapeutic areas found', 'value': 'NONE'}], []

        options = [{'label': 'ALL THERAPEUTIC AREAS', 'value': 'ALL'}]
        for ta in tas:
            options.append({'label': ta, 'value': ta})

        # Preserve selection or default to ALL
        if not current_value or len(current_value) == 0:
            return options, ['ALL']
        return options, no_update

    @app.callback(
        [Output('forecast-summary-cdu-program', 'children'),
         Output('forecast-summary-ta', 'children'),
         Output('forecast-summary-indication', 'children'),
         Output('forecast-summary-program', 'children'),
         Output('forecast-summary-project', 'children'),
         Output('forecast-summary-study-count', 'children')],
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value')]
    )
    def update_forecast_summary(project_codes, study_ids):
        """Update the forecast page summary card."""
        cdu_program = '—'
        ta = '—'
        indication = '—'
        program_name = 'None selected'
        project_text = 'None selected'
        study_count = '0'

        if not project_codes or len(project_codes) == 0:
            return cdu_program, ta, indication, program_name, project_text, study_count

        # Get list of P_Codes from selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

        if len(selected_pcodes) == 0:
            return cdu_program, ta, indication, program_name, project_text, study_count

        if len(selected_pcodes) == 1:
            project_code = selected_pcodes[0]
            program_df = core_df[core_df['P_Code'] == project_code]
            if not program_df.empty:
                program_name = program_df['Program_Name'].iloc[0]

            map_match = map_df[map_df['P_Code'] == project_code]
            if not map_match.empty:
                program_bucket = map_match.iloc[0]['Program'] if pd.notna(map_match.iloc[0]['Program']) else None

            if study_ids and len(study_ids) > 0:
                if 'ALL' in study_ids:
                    # Count only actual studies (YYYY-ZZZZ with no letters)
                    all_study_ids = core_df[core_df['P_Code'] == project_code]['Study_ID'].dropna().unique()
                    all_studies = [s for s in all_study_ids if is_actual_study(s)]
                    study_count = str(len(all_studies))
                    project_text = f'All Studies ({study_count})'

                    for study_id in all_studies:
                        match = re.match(r'\d{4}-(\d{3,4})$', str(study_id))
                        if match:
                            study_short = match.group(1)
                            matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                            if not matching_row.empty:
                                cdu = matching_row.iloc[0]['CDU'] if pd.notna(matching_row.iloc[0]['CDU']) else None
                                if cdu and program_bucket:
                                    cdu_program = f'{cdu} - {program_bucket}'
                                elif cdu:
                                    cdu_program = cdu
                                break
                else:
                    study_count = str(len(study_ids))
                    if len(study_ids) == 1:
                        project_text = get_display_name(study_ids[0], study_daily_df)
                        match = re.match(r'\d{4}-(\d{3,4})$', str(study_ids[0]))
                        if match:
                            study_short = match.group(1)
                            matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                            if not matching_row.empty:
                                cdu = matching_row.iloc[0]['CDU'] if pd.notna(matching_row.iloc[0]['CDU']) else None
                                ta = matching_row.iloc[0]['Therapeutic_Area'] if pd.notna(matching_row.iloc[0]['Therapeutic_Area']) else '—'
                                indication = matching_row.iloc[0]['Indication'] if pd.notna(matching_row.iloc[0]['Indication']) else '—'
                                if cdu and program_bucket:
                                    cdu_program = f'{cdu} - {program_bucket}'
                                elif cdu:
                                    cdu_program = cdu
                    else:
                        # Show all display names instead of count
                        study_names = [get_display_name(s, study_daily_df) for s in study_ids]
                        project_text = ', '.join(study_names)
                        indication = 'Multiple'
        else:
            program_name = f'{len(selected_pcodes)} programs selected'
            project_text = 'Multiple programs'
            indication = 'Multiple'

        return cdu_program, ta, indication, program_name, project_text, study_count

    # BSB BUDGET CALLBACKS =====================================
    @app.callback(
        [Output('bsb-total-input', 'value'),
         Output('bsb-account-breakdown', 'children')],
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value'),
         Input('forecast-account-dropdown', 'value'),
         Input('forecast-ta-dropdown', 'value'),
         Input('theme-store', 'data')]
    )
    def update_bsb_budget_info(project_codes, study_ids, account_ids, ta_selections, theme):
        """Populate BSB total and show account-level allocations."""
        # Get colors for current theme
        colors = get_colors(theme)

        if not project_codes or len(project_codes) == 0:
            return None, html.P('Select a Program to view BSB data', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})
        if not study_ids or len(study_ids) == 0:
            return None, html.P('Select a Study to view BSB data', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})
        if not account_ids or len(account_ids) == 0:
            return None, html.P('Select an Account to view BSB data', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})

        # Get P_Codes from selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

        # Filter BSB data by selection
        bsb_filtered = bsb_df[bsb_df['P_Code'].isin(selected_pcodes)].copy()

        if 'ALL' not in study_ids:
            expanded_study_ids = expand_phase_groups(study_ids, selected_pcodes)
            bsb_filtered = bsb_filtered[bsb_filtered['Study_ID'].isin(expanded_study_ids)]

        # Filter by therapeutic area if specific TAs selected
        if ta_selections and 'ALL' not in ta_selections and len(ta_selections) > 0:
            study_ids_with_ta = []
            unique_study_ids = bsb_filtered['Study_ID'].dropna().unique()
            for study_id in unique_study_ids:
                match = re.match(r'\d{4}-(\d{3,4})$', str(study_id))
                if match:
                    study_short = match.group(1)
                    matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                    if not matching_row.empty:
                        study_ta = matching_row.iloc[0]['Therapeutic_Area']
                        if pd.notna(study_ta) and study_ta in ta_selections:
                            study_ids_with_ta.append(study_id)
            bsb_filtered = bsb_filtered[bsb_filtered['Study_ID'].isin(study_ids_with_ta)]

        # Handle account filtering
        if 'Account_Clean' in bsb_filtered.columns:
            if 'PF_GROUP' in account_ids:
                pf_accounts = [acc for acc in bsb_filtered['Account_Clean'].dropna().unique() if is_program_finance_account(acc)]
                if 'ALL' not in account_ids:
                    bsb_filtered = bsb_filtered[bsb_filtered['Account_Clean'].isin(pf_accounts)]
            elif 'ALL' not in account_ids:
                bsb_filtered = bsb_filtered[bsb_filtered['Account_Clean'].isin(account_ids)]

        # Calculate total BSB
        total_bsb = bsb_filtered['Budget'].sum() if 'Budget' in bsb_filtered.columns else 0

        # Build account breakdown display
        if 'Account_Clean' in bsb_filtered.columns and 'Budget' in bsb_filtered.columns:
            account_breakdown = bsb_filtered.groupby('Account_Clean')['Budget'].sum().sort_values(ascending=False)

            breakdown_items = []
            for account, budget in account_breakdown.items():
                breakdown_items.append(
                    html.Div([
                        html.Span(f'{account}: ', style={'fontWeight': 'bold', 'color': colors['ink-strong']}),
                        html.Span(f'${budget:,.0f}', style={'color': colors['brand-cyan']})
                    ], style={'marginBottom': '6px'})
                )

            if len(breakdown_items) == 0:
                breakdown_display = html.P('No BSB data found for selection', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})
            else:
                breakdown_display = html.Div(breakdown_items)
        else:
            breakdown_display = html.P('No account data available', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})

        return total_bsb, breakdown_display


    logger.info('Forecast callbacks registered')
