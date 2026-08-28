import logging
import re
import pandas as pd
import numpy as np
from datetime import datetime
import dash
from dash import Output, Input, State, html, no_update, dcc
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
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-cdu-dropdown', 'value')],
        State('forecast-study-dropdown', 'value')
    )
    def update_forecast_studies(project_codes, cdu_selections, current_value):
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
            # Get P_Code for this study
            study_pcode = core_df[core_df['Study_ID'] == study]['P_Code'].iloc[0] if len(core_df[core_df['Study_ID'] == study]) > 0 else None

            # Filter by CDU if specified - use map_df (FULL_MAP) CDU via P_Code
            if cdu_selections and 'ALL' not in cdu_selections and study_pcode:
                study_program = map_df[map_df['P_Code'] == study_pcode]
                if not study_program.empty:
                    study_cdu = study_program.iloc[0]['CDU']
                    if not pd.notna(study_cdu) or study_cdu not in cdu_selections:
                        continue  # Skip this study if it doesn't match CDU filter

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

        # Always default to ALL STUDIES
        return options, ['ALL']

    # NOTE: Account dropdown removed - always use ALL accounts

    # UPDATE THERAPEUTIC AREA ON SELECTION =======================
    @app.callback(
        [Output('forecast-cdu-dropdown', 'options'),
         Output('forecast-cdu-dropdown', 'value')],
        Input('tabs', 'active_tab'),
        State('forecast-cdu-dropdown', 'value'))

    def update_forecast_cdus(active_tab, current_value):
        # CDU dropdown is completely independent - shows ALL CDUs from map_df (FULL_MAP)
        # Only populate when on forecast tab
        if active_tab != 'forecast':
            return no_update, no_update

        # Get ALL unique CDUs from map_df (FULL_MAP)
        cdus = map_df['CDU'].dropna().unique()
        cdus = sorted([c for c in cdus if c and c != 'Not Assigned'])

        if len(cdus) == 0:
            return [{'label': 'ALL CDUs', 'value': 'ALL'}], ['ALL']

        options = [{'label': 'ALL CDUs', 'value': 'ALL'}]
        for cdu in cdus:
            options.append({'label': cdu, 'value': cdu})

        # Default to ALL
        return options, ['ALL']

    # FILTER PROGRAMS BY CDU SELECTION =======================
    @app.callback(
        [Output('forecast-project-dropdown', 'options'),
         Output('forecast-project-dropdown', 'value')],
        Input('forecast-cdu-dropdown', 'value'),
        State('forecast-project-dropdown', 'value'))

    def filter_forecast_programs_by_cdu(cdu_selections, current_value):
        # Filter programs by CDU from map_df (FULL_MAP)
        if not cdu_selections or 'ALL' in cdu_selections:
            # Show all programs
            program_options = [{'label': 'ALL PROGRAMS', 'value': 'ALL'}]
            if map_df is not None and not map_df.empty:
                programs = map_df[['P_Code', 'Primary']].drop_duplicates()
                programs = programs[programs['P_Code'].notna() & programs['Primary'].notna()].sort_values('Primary')
                for _, row in programs.iterrows():
                    program_options.append({'label': row['Primary'], 'value': row['P_Code']})
            else:
                programs = core_df[['P_Code', 'Program_Name']].drop_duplicates()
                programs = programs[programs['P_Code'].notna()].sort_values('Program_Name')
                for _, row in programs.iterrows():
                    program_options.append({'label': row['Program_Name'], 'value': row['P_Code']})

            if not current_value or len(current_value) == 0:
                return program_options, ['ALL']
            return program_options, no_update

        # Filter programs by CDU using map_df (FULL_MAP)
        valid_pcodes = []
        if map_df is not None and not map_df.empty:
            for cdu in cdu_selections:
                matching_programs = map_df[map_df['CDU'] == cdu]
                for pcode in matching_programs['P_Code'].dropna().unique():
                    if pcode not in valid_pcodes:
                        valid_pcodes.append(pcode)

        valid_pcodes = sorted(valid_pcodes)

        if len(valid_pcodes) == 0:
            return [{'label': 'No programs found for selected CDU', 'value': 'NONE'}], []

        # Build filtered program options
        program_options = [{'label': 'ALL PROGRAMS', 'value': 'ALL'}]
        if map_df is not None and not map_df.empty:
            for pcode in valid_pcodes:
                map_match = map_df[map_df['P_Code'] == pcode]
                if not map_match.empty and pd.notna(map_match.iloc[0]['Primary']):
                    program_options.append({'label': map_match.iloc[0]['Primary'], 'value': pcode})
                else:
                    program_df = core_df[core_df['P_Code'] == pcode]
                    if not program_df.empty:
                        program_options.append({'label': program_df['Program_Name'].iloc[0], 'value': pcode})
        else:
            for pcode in valid_pcodes:
                program_df = core_df[core_df['P_Code'] == pcode]
                if not program_df.empty:
                    program_options.append({'label': program_df['Program_Name'].iloc[0], 'value': pcode})

        return program_options, ['ALL']

    # LOADING INDICATOR =============================
    @app.callback(
        Output('forecast-loading-indicator', 'children'),
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value'),
         Input('forecast-cdu-dropdown', 'value')],
        prevent_initial_call=True
    )
    def show_forecast_loading_indicator(project, study, cdu):
        return '⏳ Updating...'

    @app.callback(
        [Output('forecast-summary-cdu-program', 'children'),
         Output('forecast-summary-cdu', 'children'),
         Output('forecast-summary-indication', 'children'),
         Output('forecast-summary-program', 'children'),
         Output('forecast-summary-project', 'children'),
         Output('forecast-summary-study-count', 'children'),
         Output('forecast-summary-phase', 'children'),
         Output('forecast-summary-status', 'children'),
         Output('forecast-summary-enrollment', 'children'),
         Output('forecast-loading-indicator', 'children', allow_duplicate=True)],
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value'),
         Input('forecast-cdu-dropdown', 'value')],
        prevent_initial_call=True
    )
    def update_forecast_summary(project_codes, study_ids, cdu_selections):
        """Update the forecast page summary card."""
        cdu_program = '—'
        cdu = '—'
        indication = '—'
        program_name = 'None selected'
        project_text = 'None selected'
        study_count = '0'
        program_bucket = None
        phase = '—'
        status = '—'
        enrollment = '—'

        # Show Study/Code dropdown selection
        if study_ids and 'ALL' in study_ids:
            project_text = 'ALL STUDIES'
        elif study_ids and len(study_ids) > 0:
            # Show actual dropdown selection (even if phase groups or non-studies)
            study_display_names = [get_display_name(s, study_daily_df) if not s.startswith('PHASE_') else s.replace('PHASE_', '').replace('_', ' ') for s in study_ids]
            if len(study_display_names) == 1:
                project_text = study_display_names[0]
            else:
                project_text = f"{len(study_display_names)} Selected: {', '.join(study_display_names)}"

        if not project_codes or len(project_codes) == 0:
            # If no program selected, show CDU dropdown selection
            if cdu_selections and 'ALL' in cdu_selections:
                cdu = 'ALL CDUs'
            elif cdu_selections and len(cdu_selections) == 1:
                cdu = cdu_selections[0]
            elif cdu_selections and len(cdu_selections) > 1:
                cdu = f"{len(cdu_selections)} CDUs: {', '.join(cdu_selections)}"
            return cdu_program, cdu, indication, program_name, project_text, study_count, phase, status, enrollment, ''

        # Get list of P_Codes from selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
            # Show "ALL PROGRAMS" when ALL is selected
            program_name = 'ALL PROGRAMS'
            # When ALL programs, use CDU dropdown selection
            if cdu_selections and 'ALL' in cdu_selections:
                cdu = 'ALL CDUs'
            elif cdu_selections and len(cdu_selections) == 1:
                cdu = cdu_selections[0]
            elif cdu_selections and len(cdu_selections) > 1:
                cdu = f"{len(cdu_selections)} CDUs: {', '.join(cdu_selections)}"
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

            if len(selected_pcodes) == 0:
                return cdu_program, cdu, indication, program_name, project_text, study_count, phase, status, enrollment, ''

            if len(selected_pcodes) == 1:
                project_code = selected_pcodes[0]

                # Get Program Display Name and CDU from map_df
                map_match = map_df[map_df['P_Code'] == project_code]
                if not map_match.empty:
                    if pd.notna(map_match.iloc[0]['Primary']):
                        program_name = map_match.iloc[0]['Primary']
                    program_bucket = map_match.iloc[0]['Program'] if pd.notna(map_match.iloc[0]['Program']) else None
                    # Get CDU from map_df for this program
                    cdu_val = map_match.iloc[0]['CDU'] if pd.notna(map_match.iloc[0]['CDU']) else None
                    if cdu_val:
                        cdu = cdu_val
                        if program_bucket:
                            cdu_program = f'{cdu_val} - {program_bucket}'
                        else:
                            cdu_program = cdu_val
                else:
                    program_df = core_df[core_df['P_Code'] == project_code]
                    if not program_df.empty:
                        program_name = program_df['Program_Name'].iloc[0]
            else:
                # Multiple programs selected - show display names with count
                program_names = []
                for pcode in selected_pcodes:
                    map_match = map_df[map_df['P_Code'] == pcode]
                    if not map_match.empty and pd.notna(map_match.iloc[0]['Primary']):
                        program_names.append(map_match.iloc[0]['Primary'])
                    else:
                        program_df = core_df[core_df['P_Code'] == pcode]
                        if not program_df.empty:
                            program_names.append(program_df['Program_Name'].iloc[0])
                program_name = f"{len(program_names)} Programs: {', '.join(program_names)}" if program_names else 'Multiple programs'

        if 'ALL' in project_codes or len(selected_pcodes) == 1:
            if 'ALL' in project_codes:
                all_pcodes = selected_pcodes
                project_code = None
            else:
                project_code = selected_pcodes[0]
                all_pcodes = [project_code]

            if study_ids and len(study_ids) > 0:
                if 'ALL' in study_ids:
                    # Show "ALL STUDIES" when ALL is selected
                    project_text = 'ALL STUDIES'

                    # Count only actual studies (YYYY-ZZZZ with no letters)
                    if project_code:
                        all_study_ids = core_df[core_df['P_Code'] == project_code]['Study_ID'].dropna().unique()
                    else:
                        all_study_ids = core_df[core_df['P_Code'].isin(all_pcodes)]['Study_ID'].dropna().unique()
                    all_studies = [s for s in all_study_ids if is_actual_study(s)]
                    study_count = str(len(all_studies))

                    for study_id in all_studies:
                        match = re.match(r'\d{4}[-.](\d{3,4})$', str(study_id))
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
                    # Get actual studies from selection
                    actual_studies = [s for s in study_ids if is_actual_study(s)]
                    study_count = str(len(actual_studies))

                    if len(actual_studies) == 1:
                        # Single study - get all study info
                        match = re.match(r'\d{4}[-.](\d{3,4})$', str(actual_studies[0]))
                        if match:
                            study_short = match.group(1)
                            matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                            if not matching_row.empty:
                                indication = matching_row.iloc[0]['Indication'] if pd.notna(matching_row.iloc[0]['Indication']) else '—'
                                phase = matching_row.iloc[0]['Phase'] if pd.notna(matching_row.iloc[0]['Phase']) else '—'
                                status = matching_row.iloc[0]['Study Status (COMPASS)'] if pd.notna(matching_row.iloc[0]['Study Status (COMPASS)']) else '—'

                                # Enrollment: Actual/Planned
                                enroll_actual = matching_row.iloc[0]['# Enrollment (Actual)'] if pd.notna(matching_row.iloc[0]['# Enrollment (Actual)']) else 0
                                enroll_planned = matching_row.iloc[0]['# Enrollment (Planned)'] if pd.notna(matching_row.iloc[0]['# Enrollment (Planned)']) else 0
                                enrollment = f"{int(enroll_actual)}/{int(enroll_planned)}"
                    else:
                        # Multiple studies - show each on its own row
                        study_phases = []
                        study_statuses = []
                        study_enrollments = []

                        for study in actual_studies:
                            match = re.match(r'\d{4}[-.](\d{3,4})$', str(study))
                            if match:
                                study_short = match.group(1)
                                matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                                if not matching_row.empty:
                                    study_name = get_display_name(study, study_daily_df)
                                    study_phase = matching_row.iloc[0]['Phase'] if pd.notna(matching_row.iloc[0]['Phase']) else '—'
                                    study_status = matching_row.iloc[0]['Study Status (COMPASS)'] if pd.notna(matching_row.iloc[0]['Study Status (COMPASS)']) else '—'
                                    enroll_actual = matching_row.iloc[0]['# Enrollment (Actual)'] if pd.notna(matching_row.iloc[0]['# Enrollment (Actual)']) else 0
                                    enroll_planned = matching_row.iloc[0]['# Enrollment (Planned)'] if pd.notna(matching_row.iloc[0]['# Enrollment (Planned)']) else 0

                                    study_phases.append(f"{study_name}: {study_phase}")
                                    study_statuses.append(f"{study_name}: {study_status}")
                                    study_enrollments.append(f"{study_name}: {int(enroll_actual)}/{int(enroll_planned)}")

                        indication = 'Multiple'
                        phase = html.Div([html.Div(p, style={'marginBottom': '2px'}) for p in study_phases]) if study_phases else '—'
                        status = html.Div([html.Div(s, style={'marginBottom': '2px'}) for s in study_statuses]) if study_statuses else '—'
                        enrollment = html.Div([html.Div(e, style={'marginBottom': '2px'}) for e in study_enrollments]) if study_enrollments else '—'

        return cdu_program, cdu, indication, program_name, project_text, study_count, phase, status, enrollment, ''

    # BSB BUDGET CALLBACKS =====================================
    @app.callback(
        [Output('bsb-total-input', 'value'),
         Output('bsb-account-breakdown', 'children')],
        [Input('forecast-project-dropdown', 'value'),
         Input('forecast-study-dropdown', 'value'),
         Input('forecast-cdu-dropdown', 'value'),
         Input('theme-store', 'data')]
    )
    def update_bsb_budget_info(project_codes, study_ids, cdu_selections, theme):
        """Populate BSB total and show account-level allocations."""
        # Get colors for current theme
        colors = get_colors(theme)

        # Always use ALL accounts (no account filter dropdown)
        account_ids = ['ALL']

        if not project_codes or len(project_codes) == 0:
            return None, html.P('Select a Program to view BSB data', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})
        if not study_ids or len(study_ids) == 0:
            return None, html.P('Select a Study to view BSB data', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})

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
        if cdu_selections and 'ALL' not in cdu_selections and len(cdu_selections) > 0:
            study_ids_with_ta = []
            unique_study_ids = bsb_filtered['Study_ID'].dropna().unique()
            for study_id in unique_study_ids:
                match = re.match(r'\d{4}[-.](\d{3,4})$', str(study_id))
                if match:
                    study_short = match.group(1)
                    matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                    if not matching_row.empty:
                        study_ta = matching_row.iloc[0]['CDU']
                        if pd.notna(study_ta) and study_ta in cdu_selections:
                            study_ids_with_ta.append(study_id)
            bsb_filtered = bsb_filtered[bsb_filtered['Study_ID'].isin(study_ids_with_ta)]

        # NOTE: BSB GL breakdown should show ALL accounts regardless of Account dropdown filter
        # The account dropdown is for filtering the CHART, not the BSB breakdown
        # Do NOT filter by account here - show all accounts with BSB data

        # Calculate total BSB
        total_bsb = bsb_filtered['Budget'].sum() if 'Budget' in bsb_filtered.columns else 0

        # Build account breakdown display with improved formatting
        if 'Account_Clean' in bsb_filtered.columns and 'Budget' in bsb_filtered.columns:
            account_breakdown = bsb_filtered.groupby('Account_Clean')['Budget'].sum().sort_values(ascending=False)

            if len(account_breakdown) == 0:
                breakdown_display = html.P('No BSB data found for selection', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})
            else:
                # Create table-like structure with rows for each account
                breakdown_rows = []

                # Header row
                breakdown_rows.append(
                    html.Div([
                        html.Div('Account', style={'flex': '3', 'fontWeight': 'bold', 'fontSize': '11px', 'color': colors['ink-soft'], 'borderBottom': f'1px solid {colors["line-soft"]}', 'paddingBottom': '4px'}),
                        html.Div('BSB Amount', style={'flex': '2', 'fontWeight': 'bold', 'fontSize': '11px', 'color': colors['ink-soft'], 'textAlign': 'right', 'borderBottom': f'1px solid {colors["line-soft"]}', 'paddingBottom': '4px'}),
                        html.Div('Adjustment', style={'flex': '2', 'fontWeight': 'bold', 'fontSize': '11px', 'color': colors['ink-soft'], 'textAlign': 'right', 'borderBottom': f'1px solid {colors["line-soft"]}', 'paddingBottom': '4px', 'paddingLeft': '8px'})
                    ], style={'display': 'flex', 'marginBottom': '8px', 'alignItems': 'center'})
                )

                # Data rows with input fields
                for idx, (account, budget) in enumerate(account_breakdown.items()):
                    # Create unique ID for each account input
                    account_id = account.replace(' ', '_').replace('-', '_').replace('/', '_')

                    breakdown_rows.append(
                        html.Div([
                            html.Div(
                                account,
                                style={'flex': '3', 'fontWeight': '600', 'color': colors['ink-strong'], 'fontSize': '11px', 'paddingTop': '4px'}
                            ),
                            html.Div(
                                f'${budget:,.0f}',
                                style={'flex': '2', 'color': colors['brand-cyan'], 'fontSize': '12px', 'textAlign': 'right', 'fontWeight': 'bold', 'paddingTop': '4px'}
                            ),
                            html.Div(
                                dcc.Input(
                                    id={'type': 'bsb-adjustment-input', 'account': account, 'index': idx},
                                    type='text',
                                    placeholder='0',
                                    style={
                                        'width': '100%',
                                        'padding': '4px 6px',
                                        'fontSize': '11px',
                                        'border': f'1px solid {colors["line-soft"]}',
                                        'borderRadius': '3px',
                                        'backgroundColor': colors['surface-2'],
                                        'color': colors['ink-strong']
                                    }
                                ),
                                style={'flex': '2', 'paddingLeft': '8px'}
                            )
                        ], style={'display': 'flex', 'marginBottom': '6px', 'alignItems': 'center', 'padding': '4px 0', 'borderBottom': f'1px dotted {colors["line-soft"]}'})
                    )

                breakdown_display = html.Div(breakdown_rows)
        else:
            breakdown_display = html.P('No account data available', style={'color': colors['ink-soft'], 'fontStyle': 'italic'})

        return total_bsb, breakdown_display


    # BSB ADJUSTMENT CALLBACK =====================================
    @app.callback(
        Output('bsb-adjustments-store', 'data'),
        Input({'type': 'bsb-adjustment-input', 'account': dash.dependencies.ALL, 'index': dash.dependencies.ALL}, 'value'),
        State({'type': 'bsb-adjustment-input', 'account': dash.dependencies.ALL, 'index': dash.dependencies.ALL}, 'id'),
        prevent_initial_call=True
    )
    def store_bsb_adjustments(values, ids):
        """Store BSB adjustments keyed by account name."""
        adjustments = {}
        for val, id_dict in zip(values, ids):
            account = id_dict['account']
            if val is not None and val != '' and val != '0':
                # Convert text to number, handle commas
                try:
                    clean_val = str(val).replace(',', '').strip()
                    numeric_val = float(clean_val)
                    if numeric_val != 0:
                        adjustments[account] = numeric_val
                except (ValueError, AttributeError):
                    pass  # Skip invalid inputs
        return adjustments

    logger.info('Forecast callbacks registered')
