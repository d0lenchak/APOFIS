import logging as logger
import re
import pandas as pd
from datetime import datetime
from dash import Output, Input, State, no_update, html
import plotly.graph_objects as go
from config import COLORS, get_colors, is_program_finance_account
from data_loader import get_display_name, is_actual_study, get_study_phase


def register_actuals_callbacks(app, data):

    # get the data
    core_df = data['core_df']
    forecast_df = data['forecast_df']
    map_df = data['map_df']
    study_daily_df = data['study_daily_df']
    quarter_cols = data['quarter_cols']
    forecast_quarter_cols = data['forecast_quarter_cols']

    logger.info("Registering actuals callbacks...")

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

    # ==================== ACTUALS PAGE CALLBACKS ====================

    # UPDATE PROGRAM/STUDY ON SELECTION ============================
    @app.callback(
        [Output('actuals-study-dropdown', 'options'),
         Output('actuals-study-dropdown', 'value')],
        [Input('actuals-project-dropdown', 'value'),
         Input('actuals-cdu-dropdown', 'value')],
        State('actuals-study-dropdown', 'value'))

    def update_actuals_studies(project_codes, cdu_selections, current_value):
        if not project_codes or len(project_codes) == 0:
            return [{'label': 'Select a Program first...', 'value': 'NONE'}], []

        # filter p-code(s) of selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

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
            # Get P_Code for this specific study
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
                    'value': f'PHASE_{phase.replace(" ", "_").upper()}'})
                # Add individual studies in this phase
                for display_name, study_value in sorted(phase_buckets[phase]):
                    options.append({
                        'label': f'    {display_name}',
                        'value': study_value})

        # Always default to ALL STUDIES
        return options, ['ALL']


    # UPDATE CDU ON SELECTION =======================
    @app.callback(
        [Output('actuals-cdu-dropdown', 'options'),
         Output('actuals-cdu-dropdown', 'value')],
        Input('tabs', 'active_tab'),
        State('actuals-cdu-dropdown', 'value'))

    def update_actuals_cdus(active_tab, current_value):
        # CDU dropdown is completely independent - shows ALL CDUs from map_df (FULL_MAP)
        # Only populate when on actuals tab
        if active_tab != 'actuals':
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
        [Output('actuals-project-dropdown', 'options'),
         Output('actuals-project-dropdown', 'value')],
        Input('actuals-cdu-dropdown', 'value'),
        State('actuals-project-dropdown', 'value'))

    def filter_actuals_programs_by_cdu(cdu_selections, current_value):
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

            # Preserve current selection if valid
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

        # Reset to ALL when CDU changes
        return program_options, ['ALL']


    # LOADING INDICATOR =============================
    @app.callback(
        Output('actuals-loading-indicator', 'children'),
        [Input('actuals-project-dropdown', 'value'),
         Input('actuals-study-dropdown', 'value'),
         Input('actuals-cdu-dropdown', 'value')],
        prevent_initial_call=True
    )
    def show_loading_indicator(project, study, cdu):
        # This fires immediately when selection changes
        return '⏳ Updating...'

    # UPDATE SUMMARY ON SELECTION =============================
    @app.callback(
        [Output('actuals-summary-cdu-program', 'children'),
         Output('actuals-summary-cdu', 'children'),
         Output('actuals-summary-indication', 'children'),
         Output('actuals-summary-program', 'children'),
         Output('actuals-summary-project', 'children'),
         Output('actuals-summary-study-count', 'children'),
         Output('actuals-summary-phase', 'children'),
         Output('actuals-summary-status', 'children'),
         Output('actuals-summary-enrollment', 'children'),
         Output('actuals-loading-indicator', 'children', allow_duplicate=True)],
        [Input('actuals-project-dropdown', 'value'),
         Input('actuals-study-dropdown', 'value'),
         Input('actuals-cdu-dropdown', 'value')],
        prevent_initial_call=True)

    def update_actuals_summary(project_codes, study_ids, cdu_selections):

        # default fields
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

        # when something is selected...
        if not project_codes or len(project_codes) == 0:
            # If no program selected, show CDU dropdown selection
            if cdu_selections and 'ALL' in cdu_selections:
                cdu = 'ALL CDUs'
            elif cdu_selections and len(cdu_selections) == 1:
                cdu = cdu_selections[0]
            elif cdu_selections and len(cdu_selections) > 1:
                cdu = f"{len(cdu_selections)} CDUs: {', '.join(cdu_selections)}"
            return cdu_program, cdu, indication, program_name, project_text, study_count, phase, status, enrollment, ''

        # get p-code(s) for selection
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

            # ---> none selection
            if len(selected_pcodes) == 0:
                return cdu_program, cdu, indication, program_name, project_text, study_count, phase, status, enrollment, ''

            # ---> single selection
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

        # look up CDU, Indication
        if 'ALL' in project_codes or len(selected_pcodes) == 1:
            # Handle single program or ALL programs
            if 'ALL' in project_codes:
                # ALL PROGRAMS selected
                all_pcodes = selected_pcodes
            else:
                # Single program
                project_code = selected_pcodes[0]
                all_pcodes = [project_code]

            if study_ids and len(study_ids) > 0:
                # Expand phase groups first
                expanded_study_ids = expand_phase_groups(study_ids, all_pcodes)

                if 'ALL' in study_ids:
                    # Show "ALL STUDIES" when ALL is selected
                    project_text = 'ALL STUDIES'

                    # count actual studies
                    if 'ALL' in project_codes:
                        all_study_ids = core_df[core_df['P_Code'].isin(all_pcodes)]['Study_ID'].dropna().unique()
                    else:
                        all_study_ids = core_df[core_df['P_Code'] == project_code]['Study_ID'].dropna().unique()
                    all_studies = [s for s in all_study_ids if is_actual_study(s)]
                    study_count = str(len(all_studies))

                    # CDU already set above based on program or dropdown selection - don't override it
                else:
                    # show selected studies (use expanded list for count)
                    actual_studies = [s for s in expanded_study_ids if is_actual_study(s)]
                    study_count = str(len(actual_studies))
                    if len(actual_studies) == 1:
                        # Single study - get all study info
                        # Match YYYY-ZZZ, YYYY-ZZZZ, YYYY.ZZZ, or YYYY.ZZZZ (dash or period separator)
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
                            # Match YYYY-ZZZ, YYYY-ZZZZ, YYYY.ZZZ, or YYYY.ZZZZ (dash or period separator)
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
        else:
            # Multiple programs case already handled above
            pass

        # Clear loading indicator when done
        return cdu_program, cdu, indication, program_name, project_text, study_count, phase, status, enrollment, ''

    # UPDATE GRAPH ON SELECTION
    @app.callback(
        [Output('actuals-chart', 'figure'),
         Output('actuals-total-cost', 'children'),
         Output('actuals-total-forecasted', 'children'),
         Output('actuals-pf-total-forecasted', 'children'),
         Output('actuals-latest-cost', 'children'),
         Output('actuals-pf-total-cost', 'children'),
         Output('actuals-pf-latest-cost', 'children'),
         Output('actuals-loading-indicator', 'children', allow_duplicate=True)],
        [Input('actuals-project-dropdown', 'value'),
         Input('actuals-study-dropdown', 'value'),
         Input('actuals-cdu-dropdown', 'value'),
         Input('actuals-show-forecast', 'value'),
         Input('theme-store', 'data')],
        prevent_initial_call=True)

    def update_actuals_chart(project_codes, study_ids, cdu_selections, show_forecast, theme):
        # Always show ALL accounts
        account_codes = ['ALL']
        # Get colors for current theme
        colors = get_colors(theme)

        # Create blank figure
        fig = go.Figure()
        fig.update_layout(
            plot_bgcolor=colors['surface-2'],
            paper_bgcolor=colors['surface-2'],
            font=dict(color=colors['ink-body']),
            xaxis=dict(showgrid=True, gridcolor=colors['line-soft'], tickangle=-45),
            yaxis=dict(showgrid=True, gridcolor=colors['line-soft']),
            margin=dict(l=60, r=20, t=20, b=80),
            showlegend=True,
            legend=dict(font=dict(color=colors['ink-body'])))

        # Default values
        total_cost = '$0'
        total_forecasted = '$0'
        pf_total_forecasted = '$0'
        latest_cost = '$0'
        pf_total_cost = '$0'
        pf_latest_cost = '$0'

        # Handle multi-select programs
        if not project_codes or len(project_codes) == 0:
            return fig, total_cost, total_forecasted, pf_total_forecasted, latest_cost, pf_total_cost, pf_latest_cost, ''

        # Get list of P_Codes from selection
        if 'ALL' in project_codes:
            selected_pcodes = core_df['P_Code'].dropna().unique().tolist()
        else:
            selected_pcodes = [pc for pc in project_codes if pc != 'ALL']

        # Filter to selected programs
        filtered = core_df[core_df['P_Code'].isin(selected_pcodes)].copy()

        # Determine if we should group by Program (when multiple programs selected)
        multi_program_mode = len(selected_pcodes) > 1

        # Handle study filter (multi-select) - expand phase groups
        if study_ids and len(study_ids) > 0:
            if 'ALL' not in study_ids:
                # Expand phase group selections to individual studies
                expanded_study_ids = expand_phase_groups(study_ids, selected_pcodes)
                # Filter by specific selected studies
                filtered = filtered[filtered['Study_ID'].isin(expanded_study_ids)]

        # Handle CDU filter (multi-select)
        if cdu_selections and 'ALL' not in cdu_selections and len(cdu_selections) > 0:
            # Filter to only studies matching selected CDUs
            study_ids_with_cdu = []
            unique_study_ids = filtered['Study_ID'].dropna().unique()
            for study_id in unique_study_ids:
                match = re.match(r'\d{4}-(\d{3,4})$', str(study_id))
                if match:
                    study_short = match.group(1)
                    matching_row = study_daily_df[study_daily_df['Study_Number_Short'] == study_short]
                    if not matching_row.empty:
                        study_cdu = matching_row.iloc[0]['CDU']
                        if pd.notna(study_cdu) and study_cdu in cdu_selections:
                            study_ids_with_cdu.append(study_id)
            # Apply CDU filter to dataframe
            filtered = filtered[filtered['Study_ID'].isin(study_ids_with_cdu)]

        # Handle account filter (multi-select) - with PF_GROUP support
        account_filter_for_chart = []  # Track what to display on chart
        if account_codes and len(account_codes) > 0:
            if 'ALL' not in account_codes:
                # Check if PF_GROUP is selected
                if 'PF_GROUP' in account_codes:
                    # User selected Program Finance group - filter to PF accounts only
                    # Get all PF account codes
                    pf_account_list = [acc for acc in filtered['Account_Clean'].unique()
                                       if is_program_finance_account(acc)]
                    filtered = filtered[filtered['Account_Clean'].isin(pf_account_list)]
                    account_filter_for_chart = ['PF_GROUP']  # Special marker for grouping
                else:
                    # Filter by specific selected accounts
                    filtered = filtered[filtered['Account_Clean'].isin(account_codes)]
                    account_filter_for_chart = account_codes

        # Calculate summary stats
        total_sum = filtered[quarter_cols].sum().sum()
        total_cost = f'${total_sum:,.0f}'

        # Calculate Program Finance totals (subset of accounts managed by PF)
        filtered['is_pf'] = filtered['Account_Clean'].apply(is_program_finance_account)
        pf_filtered = filtered[filtered['is_pf'] == True]

        pf_total_sum = pf_filtered[quarter_cols].sum().sum()
        pf_total_cost = f'${pf_total_sum:,.0f}'

        pf_latest_quarter_sum = pf_filtered[quarter_cols[-1]].sum()
        pf_latest_cost = f'${pf_latest_quarter_sum:,.0f}'

        latest_quarter_sum = filtered[quarter_cols[-1]].sum()
        latest_cost = f'${latest_quarter_sum:,.0f}'

        # Get forecast data for total forecasted calculation
        forecast_filtered_for_lifespan = forecast_df[forecast_df['P_Code'].isin(selected_pcodes)]
        if study_ids and len(study_ids) > 0 and 'ALL' not in study_ids:
            forecast_filtered_for_lifespan = forecast_filtered_for_lifespan[forecast_filtered_for_lifespan['Study_ID'].isin(study_ids)]
        if account_codes and len(account_codes) > 0 and 'ALL' not in account_codes:
            if 'PF_GROUP' in account_codes:
                pf_account_list = [acc for acc in forecast_df['Account_Clean'].unique() if is_program_finance_account(acc)]
                forecast_filtered_for_lifespan = forecast_filtered_for_lifespan[forecast_filtered_for_lifespan['Account_Clean'].isin(pf_account_list)]
            else:
                forecast_filtered_for_lifespan = forecast_filtered_for_lifespan[forecast_filtered_for_lifespan['Account_Clean'].isin(account_codes)]

        # Calculate TOTAL FORECASTED (actuals + forecast combined)
        # Use filtered (already has correct filters applied and contains merged forecast data)
        future_forecast_quarters = [q for q in forecast_quarter_cols if q not in quarter_cols]
        forecast_sum = filtered[future_forecast_quarters].sum().sum() if len(future_forecast_quarters) > 0 else 0
        total_forecasted_sum = total_sum + forecast_sum
        total_forecasted = f'${total_forecasted_sum:,.0f}'

        # Calculate PF total forecasted
        pf_forecast_filtered = filtered.copy()
        pf_forecast_filtered['is_pf'] = pf_forecast_filtered['Account_Clean'].apply(is_program_finance_account)
        pf_forecast_sum = pf_forecast_filtered[pf_forecast_filtered['is_pf']][future_forecast_quarters].sum().sum() if len(future_forecast_quarters) > 0 else 0
        pf_total_forecasted_sum = pf_total_sum + pf_forecast_sum
        pf_total_forecasted = f'${pf_total_forecasted_sum:,.0f}'

        # Determine grouping for chart (now handles multi-program, multi-select and PF_GROUP)
        # MULTI-PROGRAM MODE: If multiple programs selected, show each program as a line
        if multi_program_mode:
            # Group by Program_Name to show all selected programs
            group_col = 'Program_Name'
            group_label = 'Program'
        # CONDENSED VIEW: If user selects specific studies (not ALL), show only those studies as lines
        elif study_ids and len(study_ids) > 0 and 'ALL' not in study_ids:
            # User selected specific studies - show selected studies as separate lines
            group_col = 'Study_ID'
            group_label = 'Study'
        # CONDENSED VIEW: If user selects PF_GROUP or specific accounts (not ALL), group by account
        elif account_filter_for_chart and 'PF_GROUP' in account_filter_for_chart:
            # PF_GROUP selected - show as a single "Program Finance" line
            group_col = None  # Don't group, show single line
            group_label = 'Program Finance'
        elif account_codes and len(account_codes) > 0 and 'ALL' not in account_codes and 'PF_GROUP' not in account_codes:
            # Specific accounts selected - show each account as a line
            group_col = 'Account_Clean'
            group_label = 'Account'
        # DEFAULT VIEW: Show all studies when ALL is selected
        elif 'ALL' in study_ids or not study_ids or len(study_ids) == 0:
            # Group by study for big picture view
            group_col = 'Study_ID'
            group_label = 'Study'
        else:
            # Single study and single account = single line
            group_col = None

        # Prepare forecast data if needed (for FUTURE quarters beyond actuals)
        show_forecast_data = 'show' in show_forecast if show_forecast else False

        # Get future forecast quarters (quarters NOT in actuals)
        future_forecast_quarters = [q for q in forecast_quarter_cols if q not in quarter_cols]

        # Create chart
        if group_col:
            # Multiple lines - check if we actually have multiple groups
            unique_groups = filtered[group_col].dropna().unique()
            num_groups = len(unique_groups)

            # Use Plotly's default color sequence for consistency
            plotly_colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
                             '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52']

            for idx, group_val in enumerate(filtered[group_col].dropna().unique()):
                group_data = filtered[filtered[group_col] == group_val]
                totals = group_data[quarter_cols].sum()

                # Assign color from sequence (cycle if more groups than colors)
                line_color = plotly_colors[idx % len(plotly_colors)]

                # Plot actuals line (now includes auto-filled forecast data for overlapping quarters)
                fig.add_trace(go.Scatter(
                    x=quarter_cols,
                    y=totals.values,
                    mode='lines+markers',
                    name=str(group_val),
                    line=dict(width=2, color=line_color),
                    marker=dict(size=6, color=line_color)))

                # If forecast toggle is ON, add FUTURE forecast quarters as dashed line
                if show_forecast_data and len(future_forecast_quarters) > 0:
                    # Use filtered (already has correct filters) and filter by current group value
                    group_forecast = filtered[filtered[group_col] == group_val]

                    if len(group_forecast) > 0:
                        # Get future forecast totals for this group
                        future_totals = group_forecast[future_forecast_quarters].sum()

                        # Get the last value from actuals to connect the lines
                        last_actual_value = totals.iloc[-1]

                        # Create extended x and y for forecast (connecting from last actual quarter)
                        forecast_x = [quarter_cols[-1]] + future_forecast_quarters
                        forecast_y = [last_actual_value] + future_totals.tolist()

                        # Plot future forecast (dashed, SAME COLOR as actuals line)
                        fig.add_trace(go.Scatter(
                            x=forecast_x,
                            y=forecast_y,
                            mode='lines',
                            name=f'{group_val} (Forecast)',
                            line=dict(width=2, dash='dash', color=line_color),
                            opacity=0.7,
                            showlegend=True))

            # Only add TOTAL line if there are multiple groups (>1)
            # This avoids redundant overlay when only one line exists
            if num_groups > 1:
                # Add TOTAL line (sum of all groups in FILTERED data only)
                total_across_all = filtered[quarter_cols].sum()

                fig.add_trace(go.Scatter(
                    x=quarter_cols,
                    y=total_across_all.values,
                    mode='lines+markers',
                    name='Monthly Total',
                    line=dict(color=colors['brand-cyan'], width=4, dash='dot'),
                    marker=dict(size=10, symbol='diamond')))

                # Add TOTAL forecast if toggled on
                if show_forecast_data and len(future_forecast_quarters) > 0:
                    # Use filtered (already has correct filters applied)
                    if len(filtered) > 0:
                        future_forecast_total = filtered[future_forecast_quarters].sum()

                        # Connect from last actual
                        forecast_x_total = [quarter_cols[-1]] + future_forecast_quarters
                        forecast_y_total = [total_across_all.iloc[-1]] + future_forecast_total.tolist()

                        fig.add_trace(go.Scatter(
                            x=forecast_x_total,
                            y=forecast_y_total,
                            mode='lines',
                            name='Monthly Total (Forecast)',
                            line=dict(color=colors['brand-cyan'], width=4, dash='dash'),
                            opacity=0.7))

        else:
            # Single line (could be total, single study, or Program Finance group)
            totals = filtered[quarter_cols].sum()

            # Determine line name based on what's selected
            if 'PF_GROUP' in account_filter_for_chart:
                line_name = 'Program Finance (All)'
            elif study_ids and len(study_ids) == 1 and 'ALL' not in study_ids:
                line_name = f'{study_ids[0]} (All Accounts)'
            elif account_codes and len(account_codes) == 1 and 'ALL' not in account_codes:
                line_name = account_codes[0]
            else:
                line_name = 'Total'

            # Plot actuals (includes auto-filled data)
            fig.add_trace(go.Scatter(
                x=quarter_cols,
                y=totals.values,
                mode='lines+markers',
                name=line_name,
                line=dict(color=colors['brand-cyan'], width=3),
                marker=dict(size=8),
                fill='tozeroy',
                fillcolor='rgba(0, 229, 255, 0.15)'))

            # If forecast toggle is ON, add FUTURE forecast quarters
            if show_forecast_data and len(future_forecast_quarters) > 0:
                # Use filtered (the merged core_df) instead of forecast_df
                # filtered already has the same project/study/account filters applied and contains forecast data
                if len(filtered) > 0:
                    future_totals = filtered[future_forecast_quarters].sum()

                    # Connect from last actual quarter
                    forecast_x = [quarter_cols[-1]] + future_forecast_quarters
                    forecast_y = [totals.iloc[-1]] + future_totals.tolist()

                    # Plot future forecast line (dashed, SAME COLOR as actuals - cyan)
                    fig.add_trace(go.Scatter(
                        x=forecast_x,
                        y=forecast_y,
                        mode='lines',
                        name='Forecast',
                        line=dict(color=colors['brand-cyan'], width=2, dash='dash'),
                        opacity=0.7))

        # Add running total (cumulative) on secondary axis - ALWAYS SHOW
        # Calculate cumulative total across all FILTERED data (respects all filter selections)
        total_per_quarter = filtered[quarter_cols].sum()
        cumulative_total = total_per_quarter.cumsum()

        # Add shaded area under the curve for actuals
        fig.add_trace(go.Scatter(
            x=quarter_cols,
            y=cumulative_total.values,
            mode='lines',
            name='Running Total (Filtered)',
            line=dict(color=colors['brand-green'], width=3),
            fill='tozeroy',
            fillcolor='rgba(0, 255, 156, 0.08)',
            yaxis='y2',
            hovertemplate='<b>Cumulative (Filtered)</b><br>%{y:$,.0f}<extra></extra>'
        ))

        # Extend running total into FORECAST (future quarters)
        if show_forecast_data and len(future_forecast_quarters) > 0:
            # Use filtered (already has correct filters applied)
            if len(filtered) > 0:
                # Get future quarter totals from filtered
                future_quarter_totals = filtered[future_forecast_quarters].sum()

                # Calculate cumulative starting from last actual value
                last_cumulative_value = cumulative_total.iloc[-1]
                future_cumulative = last_cumulative_value + future_quarter_totals.cumsum()

                # Connect from last actual quarter to forecasted quarters
                forecast_running_x = [quarter_cols[-1]] + future_forecast_quarters
                forecast_running_y = [last_cumulative_value] + future_cumulative.tolist()

                # Add forecasted running total line (dashed, same green)
                fig.add_trace(go.Scatter(
                    x=forecast_running_x,
                    y=forecast_running_y,
                    mode='lines',
                    name='Running Total (Forecast)',
                    line=dict(color=colors['brand-green'], width=3, dash='dash'),
                    fill='tozeroy',
                    fillcolor='rgba(0, 255, 156, 0.05)',
                    yaxis='y2',
                    opacity=0.7,
                    hovertemplate='<b>Cumulative Forecast</b><br>%{y:$,.0f}<extra></extra>'
                ))

        # Add vertical "today" line
        today = datetime.now()
        current_year = today.year
        current_quarter = (today.month - 1) // 3 + 1
        fiscal_year = current_year if today.month >= 7 else current_year - 1  # Assuming fiscal year starts in July
        current_quarter_label = f'FY{str(fiscal_year)[-2:]} Q{current_quarter}'

        # Only add the line if current quarter exists in data
        if current_quarter_label in quarter_cols:
            fig.add_vline(
                x=current_quarter_label,
                line=dict(color='rgba(255, 255, 255, 0.3)', width=2, dash='dot'),
                annotation_text='Today',
                annotation_position='top')

        # Update layout with secondary axis - ALWAYS SHOW
        fig.update_layout(
            yaxis=dict(
                title='Quarterly Cost ($)',
                showgrid=True,
                gridcolor=colors['line-soft']
            ),
            yaxis2=dict(
                title='Cumulative Total ($)',
                overlaying='y',
                side='right',
                showgrid=False,
                tickfont=dict(color=colors['brand-green'])
            ),
            margin=dict(l=60, r=100, t=20, b=80),
            legend=dict(
                orientation='v',
                yanchor='top',
                y=0.99,
                xanchor='left',
                x=0.01,
                bgcolor=colors['surface-2'],
                bordercolor=colors['line-soft'],
                font=dict(color=colors['ink-body']),
                borderwidth=1
            )
        )

        return fig, total_cost, total_forecasted, pf_total_forecasted, latest_cost, pf_total_cost, pf_latest_cost, ''
