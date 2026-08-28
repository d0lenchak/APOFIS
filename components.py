import dash_bootstrap_components as dbc
from dash import html, dcc
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
from config import COLORS, BASE_DIR

# Danielle Olenchak
# Regeneron Pharmaceuticals, Inc.

'''
Table of Contents:

I. HEADERS-------------------

II. FILTERS------------------
    IIa. Filter Elements
        (1) Title/Header
        (2) Content
            (2a) Dropdown
            (2b) Summary
            
III. HOME TAB----------------
    IIIa. Cards
    IIIb. Line Chart
    
IV. BSB METER TAB------------
    IVa. Pop-Out/Modal Window to view data as table
    IVb. Gauge & Cards
        (1) Gauge Chart
        (2) Summary Card
        (3) Detailed Summary Cards
    IVc. Stacked Bar Chart

V. FORECAST TAB------------

'''


# HELPER FUNCTIONS
#==========================================================================================
def load_help_content():
    help_file = BASE_DIR / 'help_content.txt'
    try:
        with open(help_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return "Help content file not found. Please contact support."
    except Exception as e:
        return f"Error loading help content: {str(e)}"


def create_help_modal(page_prefix, colors=None):
    if colors is None:
        colors = COLORS
    help_text = load_help_content()

    # Convert text content to formatted HTML
    lines = help_text.split('\n')
    formatted_content = []

    for line in lines:
        if line.strip() == '':
            formatted_content.append(html.Br())
        elif line.startswith('==='):
            continue
        elif line.startswith('---'):
            formatted_content.append(html.Hr(style={'borderColor': colors['line-soft'], 'margin': '12px 0'}))
        elif line.endswith('---') or line.endswith('==='):
            formatted_content.append(html.H5(line.replace('-', '').replace('=', '').strip(),
                                            style={'color': colors['brand-cyan'],
                                                   'marginTop': '16px',
                                                   'marginBottom': '8px',
                                                   'fontWeight': 'bold'}))
        elif line.startswith('•'):
            formatted_content.append(html.P(line, style={'color': colors['ink-body'],
                                                          'fontSize': '13px',
                                                          'marginLeft': '12px',
                                                          'marginBottom': '6px'}))
        else:
            formatted_content.append(html.P(line, style={'color': colors['ink-body'],
                                                          'fontSize': '13px',
                                                          'marginBottom': '8px'}))

    return dbc.Modal([
        dbc.ModalHeader(
            dbc.ModalTitle('APOFIS Help & Tips'),
            style={'backgroundColor': colors['surface-0']}),
        dbc.ModalBody(
            html.Div(formatted_content,
                    style={'backgroundColor': colors['surface-2'],
                           'padding': '20px',
                           'maxHeight': '500px',
                           'overflowY': 'auto'}),
            style={'backgroundColor': colors['surface-2']}),
        dbc.ModalFooter(
            dbc.Button('Close', id=f'{page_prefix}-help-close-btn', className='ms-auto', n_clicks=0),
            style={'backgroundColor': colors['surface-0']}),
    ],
    id=f'{page_prefix}-help-modal',
    size='lg',
    scrollable=True,
    style={'backgroundColor': colors['surface-2']})


# I. HEADERS
#==========================================================================================
def create_header(colors=None, theme='dark'):
    if colors is None:
        colors = COLORS
    # Set toggle value based on current theme
    toggle_value = ['light'] if theme == 'light' else []

    return html.Div(style={
        'position': 'relative',
        'padding': '10px',
        'borderBottom': f'1px solid {colors["line-soft"]}',
        'marginBottom': '10px',
        'minHeight': '90px'},
        children=[
            # regn logo in top left
            html.Img(
                src='/assets/regn-transparent-logo.png',
                style={
                    'position': 'absolute',
                    'left': '10px',
                    'top': '8px',
                    'height': '70px',
                    'width': 'auto'
                }),
            # theme toggle in top right
            html.Div(style={
                'position': 'absolute',
                'right': '20px',
                'top': '20px'
            }, children=[
                dbc.Checklist(
                    id='theme-toggle',
                    options=[{'label': ' Light Mode', 'value': 'light'}],
                    value=toggle_value,
                    switch=True,
                    style={'fontSize': '14px', 'color': colors['ink-body']}
                )
            ]),
            # center the content - stars and title
            html.Div(style={'textAlign': 'center', 'paddingTop': '8px'}, children=[
                html.Div(style={'display': 'inline-block', 'verticalAlign': 'top'}, children=[
                    # Stars on left - smaller, white, positioned at top
                    html.Span('. ✦ ˖˚',
                        style={'color': 'white',
                               'fontSize': '16px',
                               'marginRight': '12px',
                               'fontWeight': '300',
                               'letterSpacing': '1px',
                               'verticalAlign': 'top',
                               'display': 'inline-block',
                               'marginTop': '0px'}),
                    # APOFIS title - large and blue
                    html.Span('APOFIS',
                        style={'color': colors['regn-blue'],
                               'fontSize': '54px',
                               'fontWeight': 'bold',
                               'letterSpacing': '3px',
                               'display': 'inline-block'}),
                    # Stars on right - smaller, white, positioned at top
                    html.Span('˚. ✦ .',
                        style={'color': 'white',
                               'fontSize': '16px',
                               'marginLeft': '12px',
                               'fontWeight': '300',
                               'letterSpacing': '1px',
                               'verticalAlign': 'top',
                               'display': 'inline-block',
                               'marginTop': '0px'})]),
                html.P('Actuals-Powered Forecast Interface Solution',
                    style={'color': colors['ink-soft'],
                           'fontSize': '14px',
                           'marginTop': '5px',
                           'marginBottom': '0',
                           'fontWeight': 'bold',
                           'marginTop': '0px'})
            ])
        ])


# II. FILTERS (all tabs)
#==========================================================================================
def create_filters(page_prefix, button_text, button_color, core_df, map_df=None, colors=None):
    if colors is None:
        colors = COLORS

    # match "Program" buckets from map_df
    program_options = [{'label': 'ALL PROGRAMS', 'value': 'ALL'}]

    if map_df is not None and not map_df.empty:
        programs = map_df[['P_Code', 'Primary']].drop_duplicates()
        programs = programs[programs['P_Code'].notna() & programs['Primary'].notna()].sort_values('Primary')
        for _, row in programs.iterrows():
            program_options.append({'label': row['Primary'], 'value': row['P_Code']})

    # otherwise just use the value from core_df
    else:
        programs = core_df[['P_Code', 'Program_Name']].drop_duplicates()
        programs = programs[programs['P_Code'].notna()].sort_values('Program_Name')
        for _, row in programs.iterrows():
            program_options.append({'label': row['Program_Name'], 'value': row['P_Code']})


    # IIa. Filter Elements
    #===============================================================
    return html.Div([

        # (1) Title/Header
        dbc.Row([
            dbc.Col([
                html.H5('Filters', style={'color': colors['ink-body'],
                                          'marginBottom': '10px',
                                          'fontSize': '13px',
                                          'fontWeight': '600',
                                          'letterSpacing': '0.5px'})], width=8),
            dbc.Col([
                dbc.Button(
                    '❓ Help',
                    id=f'{page_prefix}-help-btn',
                    color='info',
                    outline=True,
                    size='sm',
                    style={'float': 'right', 'fontSize': '11px'})], width=4)]),
        
        # (2) Content --------------------------------------------
        dbc.Card([
            dbc.CardBody([
            dbc.Row([

            # (2a) Dropdowns (Left Column) ----------------------
                dbc.Col([

                    # CDU (optional filter - can be set before selecting programs)
                    dbc.Row([
                        dbc.Col([
                            html.Label('CDU (Optional)', style={'color': colors['ink-body'], 'marginBottom': '4px', 'fontSize': '11px'}),
                            dcc.Dropdown(
                                id=f'{page_prefix}-cdu-dropdown',
                                options=[{'label': 'ALL CDUs', 'value': 'ALL'}],
                                value=['ALL'],
                                multi=True,
                                placeholder='Filter by CDU (optional)...',
                                maxHeight=400,
                                style={'marginBottom': '6px', 'fontSize': '12px'})], md=12),]),

                    # PROGRAM (multi-select)
                    dbc.Row([
                        dbc.Col([
                            html.Label('Program', style={'color': colors['ink-body'], 'marginBottom': '4px', 'fontSize': '11px'}),
                            dcc.Dropdown(
                                id=f'{page_prefix}-project-dropdown',
                                options=program_options,
                                value=['ALL'],
                                multi=True,
                                placeholder='Select programs...',
                                maxHeight=400,
                                style={'marginBottom': '6px', 'fontSize': '12px'})], md=12),]),

                    # STUDY (multi-select)
                    dbc.Row([
                        dbc.Col([
                            html.Label('Study', style={'color': colors['ink-body'], 'marginBottom': '4px', 'fontSize': '11px'}),
                            dcc.Dropdown(
                                id=f'{page_prefix}-study-dropdown',
                                options=[{'label': 'Select a Project first...', 'value': 'NONE'}],
                                value=['ALL'],
                                multi=True,
                                placeholder='Select studies...',
                                maxHeight=400,
                                style={'marginBottom': '0', 'fontSize': '12px'})], md=12),])], md=4),


            # (2b) Summary (Right Column) ----------------------
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([

                        # Title with loading indicator
                            html.Div([
                                html.H5('Selection Summary', style={'color': colors['ink-strong'], 'marginBottom': '0', 'fontSize': '14px', 'fontWeight': 'bold', 'display': 'inline-block'}),
                                html.Span(id=f'{page_prefix}-loading-indicator', children='',
                                         style={'marginLeft': '12px', 'fontSize': '13px', 'fontWeight': '600', 'color': '#00E5FF', 'display': 'inline-block'})
                            ], style={'marginBottom': '10px'}),

                        # Content
                            dbc.Row([
                                # CDU - Target
                                dbc.Col([
                                    html.P('CDU - Target', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.P(id=f'{page_prefix}-summary-cdu-program', children='—',
                                           style={'fontSize': '16px', 'color': colors['ink-strong'], 'marginBottom': '0'})], md=4),
                                # CDU
                                dbc.Col([
                                    html.P('CDU', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.P(id=f'{page_prefix}-summary-cdu', children='—',
                                           style={'fontSize': '16px', 'color': colors['ink-strong'], 'marginBottom': '0'})], md=4),
                                # Indication
                                dbc.Col([
                                    html.P('Indication', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.P(id=f'{page_prefix}-summary-indication', children='—',
                                           style={'fontSize': '16px', 'color': colors['ink-strong'], 'marginBottom': '0'})], md=4),], style={'marginBottom': '8px'}),
                    
                            dbc.Row([
                                # Program
                                dbc.Col([
                                    html.P('Program', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.Div(id=f'{page_prefix}-summary-program', children='None selected',
                                           style={'fontSize': '14px', 'color': colors['ink-strong'], 'marginBottom': '0', 'maxHeight': '60px', 'overflowY': 'auto', 'overflowX': 'hidden', 'wordBreak': 'break-word'})], md=4),
                                # Study/Code
                                dbc.Col([
                                    html.P('Study/Code', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.Div(id=f'{page_prefix}-summary-project', children='None selected',
                                           style={'fontSize': '14px', 'color': colors['ink-strong'], 'marginBottom': '0', 'maxHeight': '60px', 'overflowY': 'auto', 'overflowX': 'hidden', 'wordBreak': 'break-word'})], md=4),
                                # Study-Specific Codes
                                dbc.Col([
                                    html.P('Study-Specific Codes', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.P(id=f'{page_prefix}-summary-study-count', children='0',
                                           style={'fontSize': '16px', 'color': colors['brand-cyan'], 'marginBottom': '0'})
                                ], md=4),
                            ], style={'marginBottom': '8px'}),

                            # Study View section
                            html.Div([
                                html.P('Study View', style={'fontSize': '11px', 'color': colors['ink-soft'], 'fontWeight': 'bold', 'marginBottom': '6px', 'marginTop': '6px'})
                            ]),
                            dbc.Row([
                                # Phase
                                dbc.Col([
                                    html.P('Phase', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.Div(id=f'{page_prefix}-summary-phase', children='—',
                                           style={'fontSize': '14px', 'color': colors['ink-strong'], 'marginBottom': '0', 'maxHeight': '60px', 'overflowY': 'auto', 'overflowX': 'hidden', 'wordBreak': 'break-word'})], md=4),
                                # Status
                                dbc.Col([
                                    html.P('Status', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.Div(id=f'{page_prefix}-summary-status', children='—',
                                           style={'fontSize': '14px', 'color': colors['ink-strong'], 'marginBottom': '0', 'maxHeight': '60px', 'overflowY': 'auto', 'overflowX': 'hidden', 'wordBreak': 'break-word'})], md=4),
                                # Enrollment
                                dbc.Col([
                                    html.P('Enrollment', style={'fontSize': '10px', 'color': colors['ink-soft'], 'fontStyle': 'italic', 'marginBottom': '2px'}),
                                    html.Div(id=f'{page_prefix}-summary-enrollment', children='—',
                                           style={'fontSize': '14px', 'color': colors['ink-strong'], 'marginBottom': '0', 'maxHeight': '60px', 'overflowY': 'auto', 'overflowX': 'hidden', 'wordBreak': 'break-word'})], md=4),
                            ], style={'marginBottom': '0'}),
                        ], style={'padding': '12px'})
                    ], style={'backgroundColor': colors['surface-2'], 'height': '100%'})
                ], md=8)
            ])
        ], style={'padding': '18px'})], style={'backgroundColor': colors['surface-2'], 'borderRadius': '4px'})
    ], style={'marginBottom': '16px'})


# III. HOME TAB
#==========================================================================================
def create_actuals_page(core_df, map_df=None, colors=None):
    if colors is None:
        colors = COLORS
    return html.Div(style={'background': colors['surface-0'], 'minHeight': '100vh', 'padding': '20px'}, children=[
        # Help Modal
        create_help_modal('actuals', colors),

        create_filters('actuals', '📤 Send Filters to Forecast', 'info', core_df, map_df, colors),

        # IIIa. Cards
        #===============================================================
        dbc.Row([

            # Last Quarter Spend
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('LAST QUARTER SPEND', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='actuals-latest-cost', children='$0', style={
                            'color': colors['ink-strong'],
                            'fontSize': '32px',
                            'margin': '0'}),
                        html.Hr(style={
                            'borderColor': colors['line-soft'],
                            'margin': '12px 0'}),
                        html.P('Program Finance Total', style={
                            'fontSize': '10px',
                            'color': colors['ink-soft'],
                            'marginBottom': '6px',
                            'fontWeight': '600'}),
                        html.H4(id='actuals-pf-latest-cost', children='$0', style={
                            'color': colors['brand-cyan'],
                            'fontSize': '20px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=4, md=6, className='mb-3'),

            # Historical Spend
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('HISTORICAL SPEND', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='actuals-total-cost', children='$0', style={
                            'color': colors['ink-strong'],
                            'fontSize': '32px',
                            'margin': '0'}),
                        html.Hr(style={
                            'borderColor': colors['line-soft'],
                            'margin': '12px 0'}),
                        html.P('Program Finance Total', style={
                            'fontSize': '10px',
                            'color': colors['ink-soft'],
                            'marginBottom': '6px',
                            'fontWeight': '600'}),
                        html.H4(id='actuals-pf-total-cost', children='$0', style={
                            'color': colors['brand-cyan'],
                            'fontSize': '20px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=4, md=6, className='mb-3'),

            # Cumulative Forecast Spend
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('CUMULATIVE FORECASTED SPEND', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='actuals-total-forecasted', children='$0', style={
                            'color': colors['ink-strong'],
                            'fontSize': '32px',
                            'margin': '0'}),
                        html.Hr(style={
                            'borderColor': colors['line-soft'],
                            'margin': '12px 0'}),
                        html.P('Program Finance Total', style={
                            'fontSize': '10px',
                            'color': colors['ink-soft'],
                            'marginBottom': '6px',
                            'fontWeight': '600'}),
                        html.H4(id='actuals-pf-total-forecasted', children='$0', style={
                            'color': colors['brand-cyan'],
                            'fontSize': '20px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=4, md=6, className='mb-3'),]),


        # IIIb. FIGURE
        #===============================================================
        dbc.Card([
            dbc.CardBody([
                dbc.Row([

                    # Title
                    dbc.Col([
                        html.H4('Quarterly Financials', style={
                            'color': colors['ink-strong'],
                            'fontSize': '32px',
                            'marginBottom': '16px'})], width=8),
                    
                    # Show Forecast Button
                    dbc.Col([
                        dbc.Checklist(
                            id='actuals-show-forecast',
                            options=[{'label': ' Show Future Forecast', 'value': 'show'}],
                            value=[],
                            switch=True,
                            style={'float': 'right', 'marginTop': '8px'})], width=4)]),

                # Line Chart
                dcc.Graph(
                    id='actuals-chart',
                    style={'height': '400px'},
                    config={'displayModeBar': True, 'displaylogo': False})])],
            style={'backgroundColor': colors['surface-2'], 'marginTop': '20px'}),])



# IV. BSB METER TAB
#==========================================================================================
def create_bsb_page(core_df, map_df=None, colors=None):
    if colors is None:
        colors = COLORS
    return html.Div(style={'background': colors['surface-0'], 'minHeight': '100vh', 'padding': '20px'}, children=[
        # Help Modal
        create_help_modal('bsb', colors),

        create_filters('bsb', '📊 Blue Sheet Budget Analysis', 'primary', core_df, map_df, colors),

        
        # IVa. Pop-Out/Modal Window to view data as table
        #===============================================================
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle('Filtered Data Summary')),
            dbc.ModalBody([
                html.Div(id='bsb-data-table-container')]),
            dbc.ModalFooter(
                dbc.Button('Close', id='bsb-close-modal-btn', className='ms-auto', n_clicks=0)),],
        id='bsb-data-modal',
        size='xl',
        scrollable=True),

        # IVb. Gauge and Cards
        #===============================================================
        dbc.Row([
            
            # (1) Gauge (left) ------------------------------------------
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dcc.Graph(
                            id='bsb-gauge-combined',
                            config={'displayModeBar': False},
                            style={'height': '420px'})])],
                    style={'backgroundColor': colors['surface-2'], 'padding': '20px', 'minHeight': '520px'})],
                lg=7, md=7, className='mb-3'),

            # (2) Summary Card (right) ----------------------------------
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([

                    # COMMITTED SPEND
                        html.Div([
                            html.P('COMMITTED SPEND', style={
                                'fontSize': '11px',
                                'color': colors['ink-soft'],
                                'marginBottom': '4px',
                                'fontWeight': '600',
                                'letterSpacing': '1px'}),
                            
                            html.Div([
                                # Committed total (open POs + any actuals)
                                html.H2(id='bsb-committed-total', children='$0', style={
                                    'color': colors['brand-green'],
                                    'fontSize': '28px',
                                    'margin': '0',
                                    'fontWeight': 'bold'}),
                                # Actuals Realized
                                html.P(id='bsb-actuals-spent', children='   $0 realized (0%)', style={
                                    'color': colors['ink-strong'],
                                    'fontSize': '13px',
                                    'margin': '2px 0 2px 0',
                                    'fontStyle': 'italic',
                                    'fontWeight': 'normal'}),
                                # BSB Remaining
                                html.P(id='bsb-committed-remaining', children=' $0 remaining', style={
                                    'color': colors['ink-strong'],
                                    'fontSize': '13px',
                                    'margin': '2px 0 12px 0',
                                    'fontStyle': 'italic',
                                    'fontWeight': 'normal'})])]),

                    # FORECASTED TOTAL
                        html.Div([
                            html.P('FORECAST ALONE', style={
                                'fontSize': '11px',
                                'color': colors['ink-soft'],
                                'marginBottom': '4px',
                                'fontWeight': '600',
                                'letterSpacing': '1px'}),
                            html.H2(id='bsb-total-forecasted', children='$0', style={
                                'color': colors['brand-cyan'],
                                'fontSize': '28px',
                                'margin': '0 0 16px 0',
                                'fontWeight': 'bold'})]),

                        html.Hr(style={'margin': '16px 0', 'borderColor': colors['line-soft'], 'borderWidth': '2px'}),

                    # PROJECTED TOTAL
                        html.Div([
                            html.P('PROJECTED TOTAL', style={
                                'fontSize': '11px',
                                'color': colors['ink-soft'],
                                'marginBottom': '4px',
                                'fontWeight': '600',
                                'letterSpacing': '1px'}),
                            html.H1(id='bsb-projected-total', children='$0', style={
                                'color': colors['ink-strong'],
                                'fontSize': '36px',
                                'margin': '0 0 8px 0',
                                'fontWeight': 'bold'}),
                            # delta between BSB (planned) total and forecasted total
                            html.P(id='bsb-delta', children='▼ $0 (0.0%)', style={
                                'fontSize': '16px',
                                'margin': '2px 0 2px 0',
                                'fontWeight': 'bold'})]),

                        html.Hr(style={'margin': '16px 0', 'borderColor': colors['line-soft'], 'borderWidth': '2px'}),

                    # BUDGET (BSB)
                        html.Div([
                            html.P('BUDGET (BSB)', style={
                                'fontSize': '11px',
                                'color': colors['ink-soft'],
                                'marginBottom': '4px',
                                'fontWeight': '600',
                                'letterSpacing': '1px'}),
                            html.H1(id='bsb-total-budget', children='$0', style={
                                'color': colors['ink-strong'],
                                'fontSize': '36px',
                                'margin': '0',
                                'fontWeight': 'bold'})])])],
                         
                    style={'backgroundColor': colors['surface-2'],
                           'padding': '30px',
                           'minHeight': '520px'})],
                lg=5, md=5, className='mb-3'),]),


        # (3) DETAILED SUMMARY CARDS -------------------------------------------
        dbc.Row([
            
            # Budget Remaining
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('BUDGET REMAINING', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='bsb-remaining', children='$0', style={
                            'color': colors['brand-green'],
                            'fontSize': '32px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=3, md=6, className='mb-3'),

            # Burn Rate
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('AVG QUARTERLY BURN', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='bsb-burn-rate', children='$0/qtr', style={
                            'color': colors['ink-strong'],
                            'fontSize': '28px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=3, md=6, className='mb-3'),

            # Overrun Risk
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('OVERRUN RISK', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='bsb-overrun', children='0%', style={
                            'color': colors['ink-strong'],
                            'fontSize': '32px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=3, md=6, className='mb-3'),

            # Quarters to Depletion
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.P('QUARTERS TO DEPLETION', style={
                            'fontSize': '11px',
                            'color': colors['ink-soft'],
                            'marginBottom': '12px',
                            'fontWeight': '600'}),
                        html.H2(id='bsb-quarters-left', children='N/A', style={
                            'color': colors['ink-strong'],
                            'fontSize': '32px',
                            'margin': '0'})])],
                    style={'backgroundColor': colors['surface-2']})],
                lg=3, md=6, className='mb-3'),]),


        # IVc. Stacked Bar Chart
        #===============================================================
        dbc.Card([
            dbc.CardBody([
                # Header with title and button
                dbc.Row([
                    dbc.Col([
                        html.H4('Account Budget Analysis: BSB vs Actuals vs Forecasted', style={
                            'color': colors['ink-strong'],
                            'marginBottom': '16px'})
                    ], width=8),
                    dbc.Col([
                        dbc.Button(
                            '📊 View Filtered Data',
                            id='bsb-view-data-btn',
                            color='info',
                            outline=True,
                            size='sm',
                            style={'float': 'right'})
                    ], width=4)
                ]),
                dcc.Graph(
                    id='bsb-stacked-bar',
                    config={'displayModeBar': False},
                    style={'height': '500px'})])],
            style={'backgroundColor': colors['surface-2'], 'marginTop': '20px'}),
    ])


# IV. FORECAST TAB
#==========================================================================================
def create_forecast_page(core_df, map_df=None, colors=None):
    if colors is None:
        colors = COLORS

    return html.Div(style={'background': colors['surface-0'], 'minHeight': '100vh', 'padding': '20px'}, children=[
        # Help Modal
        create_help_modal('forecast', colors),

        create_filters('forecast', '📥 Send Filters to Actuals', 'success', core_df, map_df, colors),

        # Ongoing Studies Forecast content (no tabs)
        create_study_forecast_tab(colors)])


def create_study_forecast_tab(colors=None):
    if colors is None:
        colors = COLORS

    # Blank forecast figure
    forecast_fig = go.Figure()
    forecast_fig.update_layout(
        plot_bgcolor=colors['surface-2'],
        paper_bgcolor=colors['surface-2'],
        font=dict(color=colors['ink-body']),
        xaxis=dict(showgrid=True, gridcolor=colors['line-soft'], title='Quarter'),
        yaxis=dict(showgrid=True, gridcolor=colors['line-soft'], title='Amount ($)'),
        margin=dict(l=60, r=20, t=20, b=80),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))

    return html.Div([
        # Forecast Configuration Card
        dbc.Card([
            dbc.CardBody([
                html.H4('Forecast Details', style={'color': colors['ink-strong'], 'marginBottom': '20px'}),

                dbc.Row([
                    # Forecast Method Column
                    dbc.Col([
                        html.Label('Forecast Details', style={'color': colors['ink-body'], 'marginBottom': '8px', 'fontWeight': '600'}),
                        dcc.Dropdown(
                            id='forecast-method',
                            options=[
                                {'label': 'Machine Learning (Milestone-Based)', 'value': 'context'},
                                {'label': 'Bell Curve (Milestone-Based)', 'value': 'bell'},
                                {'label': 'Linear', 'value': 'linear'},
                                {'label': 'Polynomial', 'value': 'polynomial'},
                                {'label': 'Exponential Smoothing', 'value': 'exponential'},
                                {'label': 'Monte Carlo', 'value': 'monte_carlo'},
                                {'label': 'Random Forest', 'value': 'tree'}],
                            value='context',  # Default to context-aware
                            clearable=False,
                            style={'marginBottom': '16px'})
                    ], md=4),

                    # Forecast Info Column
                    dbc.Col([
                        html.Label('Forecast Period', style={'color': colors['ink-body'], 'marginBottom': '8px', 'fontWeight': '600'}),
                        html.P('***Automatically forecasts through 2Q after DBL. Accounts always broken out by default.',
                               style={'color': colors['brand-cyan'], 'fontSize': '13px', 'fontStyle': 'italic', 'marginTop': '8px'}),
                    ], md=12),
                ])
            ])
        ], style={'backgroundColor': colors['surface-2'], 'marginBottom': '20px'}),

        # Budget & Timeline Card (2 Columns)
        dbc.Card([
            dbc.CardBody([
                html.H4('Study Information', style={'color': colors['ink-strong'], 'marginBottom': '10px'}),
                html.P([
                    html.I(className='fas fa-info-circle', style={'marginRight': '8px'}),
                    'Values auto-populate from source data. Edit to create "what-if" scenarios.'
                ], style={'color': colors['ink-soft'], 'fontSize': '14px', 'marginBottom': '20px'}),

                dbc.Row([
                    # LEFT COLUMN: BUDGET
                    dbc.Col([
                        html.H5('BSB', style={'color': colors['brand-cyan'], 'marginBottom': '16px', 'fontWeight': 'bold'}),

                        # Total BSB Entry
                        html.Label('Total BSB', style={'color': colors['ink-body'], 'fontSize': '13px', 'fontWeight': '600'}),
                        dcc.Input(
                            id='bsb-total-input',
                            type='number',
                            placeholder='Auto-populates from BSB data',
                            style={'width': '100%', 'marginBottom': '16px', 'padding': '8px', 'fontSize': '14px'}
                        ),

                        # Account Allocations Display
                        html.Label('GL Account Breakdown', style={'color': colors['ink-body'], 'fontSize': '13px', 'fontWeight': '600', 'marginTop': '12px'}),
                        html.P('Adjustments: Add positive/negative values to influence forecast amounts',
                               style={'color': colors['ink-soft'], 'fontSize': '10px', 'fontStyle': 'italic', 'marginTop': '4px', 'marginBottom': '8px'}),
                        html.Div(
                            id='bsb-account-breakdown',
                            style={
                                'backgroundColor': colors['surface-0'],
                                'padding': '12px',
                                'borderRadius': '4px',
                                'border': f'1px solid {COLORS["line-soft"]}',
                                'fontSize': '12px',
                                'color': colors['ink-body'],
                                'marginBottom': '12px'
                            }
                        )
                    ], md=6),

                    # RIGHT COLUMN: TIMELINE
                    dbc.Col([
                        html.H5('Milestones (SDR)', style={'color': colors['brand-cyan'], 'marginBottom': '16px', 'fontWeight': 'bold'}),

                        dbc.Row([
                            dbc.Col([
                                html.Label('FPFV (First Patient First Visit)', style={'color': colors['ink-body'], 'fontSize': '11px', 'fontWeight': '600'}),
                                dcc.DatePickerSingle(
                                    id='fpfv-date',
                                    placeholder='Select date...',
                                    display_format='YYYY-MM-DD',
                                    style={'width': '100%', 'marginBottom': '8px'}
                                )
                            ], md=12),
                        ]),

                        dbc.Row([
                            dbc.Col([
                                html.Label('FPFD (First Patient First Dose)', style={'color': colors['ink-body'], 'fontSize': '11px', 'fontWeight': '600'}),
                                dcc.DatePickerSingle(
                                    id='fpfd-date',
                                    placeholder='Select date...',
                                    display_format='YYYY-MM-DD',
                                    style={'width': '100%', 'marginBottom': '8px'}
                                )
                            ], md=12),
                        ]),

                        dbc.Row([
                            dbc.Col([
                                html.Label('LPFD (Last Patient First Dose)', style={'color': colors['ink-body'], 'fontSize': '11px', 'fontWeight': '600'}),
                                dcc.DatePickerSingle(
                                    id='lpfd-date',
                                    placeholder='Select date...',
                                    display_format='YYYY-MM-DD',
                                    style={'width': '100%', 'marginBottom': '8px'}
                                )
                            ], md=12),
                        ]),

                        dbc.Row([
                            dbc.Col([
                                html.Label('LPLV (Last Patient Last Visit)', style={'color': colors['ink-body'], 'fontSize': '11px', 'fontWeight': '600'}),
                                dcc.DatePickerSingle(
                                    id='lplv-date',
                                    placeholder='Select date...',
                                    display_format='YYYY-MM-DD',
                                    style={'width': '100%', 'marginBottom': '8px'}
                                )
                            ], md=12),
                        ]),

                        dbc.Row([
                            dbc.Col([
                                html.Label('DBL (Database Lock)', style={'color': colors['ink-body'], 'fontSize': '11px', 'fontWeight': '600'}),
                                dcc.DatePickerSingle(
                                    id='dbl-date',
                                    placeholder='Select date...',
                                    display_format='YYYY-MM-DD',
                                    style={'width': '100%', 'marginBottom': '8px'}
                                )
                            ], md=12),
                        ]),
                    ], md=6),
                ]),

                # Action buttons
                dbc.Row([
                    dbc.Col([
                        dbc.Button(
                            [html.I(className='fas fa-undo', style={'marginRight': '8px'}), 'Reset to Original'],
                            id='reset-milestones-btn',
                            color='secondary',
                            outline=True,
                            size='md',
                            style={'marginTop': '10px', 'marginRight': '10px'}
                        ),
                        dbc.Button(
                            [html.I(className='fas fa-chart-line', style={'marginRight': '8px'}), 'Generate Forecast'],
                            id='generate-forecast-btn',
                            color='success',
                            size='md',
                            style={'marginTop': '10px', 'marginRight': '10px'}
                        )
                    ], md=12)
                ])
            ])
        ], style={'backgroundColor': colors['surface-2'], 'marginBottom': '20px'}),

        # Hidden stores for custom forecast data and BSB adjustments
        dcc.Store(id='custom-forecast-store', data=None),
        dcc.Store(id='editing-point-store', data=None),
        dcc.Store(id='bsb-adjustments-store', data={}),
        dcc.Store(id='monthly-table-store', data=None),

        # Forecast Output - Chart
        dbc.Card([
            dbc.CardBody([
                html.H4('Forecast Projection', style={'color': colors['ink-strong'], 'marginBottom': '16px'}),
                html.Div(id='forecast-instructions', style={'marginBottom': '10px'}),

                # Point editor (appears when clicking a point)
                html.Div(id='point-editor', style={'marginBottom': '10px'}),

                # Chart Display Options (Post-Generation Toggles)
                html.Div([
                    html.Label('Chart Display Options:', style={'color': colors['ink-soft'], 'marginRight': '15px', 'fontSize': '13px', 'fontWeight': '600'}),
                    dbc.Checklist(
                        id='show-account-lines-toggle',
                        options=[{'label': ' Show Account Lines', 'value': 'show'}],
                        value=[],
                        inline=True,
                        style={'display': 'inline-block', 'marginRight': '15px'}),
                    dbc.Checklist(
                        id='show-confidence-toggle',
                        options=[{'label': ' Confidence Interval', 'value': 'show'}],
                        value=[],
                        inline=True,
                        style={'display': 'inline-block', 'marginRight': '15px'}),
                    dbc.Checklist(
                        id='show-previous-forecast-toggle',
                        options=[{'label': ' Previous Forecast', 'value': 'show'}],
                        value=[],
                        inline=True,
                        style={'display': 'inline-block'})
                ], style={'marginBottom': '10px', 'padding': '10px', 'backgroundColor': colors['surface-0'], 'borderRadius': '4px'}),

                dcc.Graph(
                    id='forecast-chart',
                    figure=forecast_fig,
                    style={'height': '450px'},
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'toImageButtonOptions': {
                            'format': 'png',
                            'filename': 'apofis_forecast',
                            'height': 600,
                            'width': 1200,
                            'scale': 2
                        }
                    }
                )
            ])
        ], style={'backgroundColor': colors['surface-2'], 'marginBottom': '20px'}),

        # Forecast Output - Account Breakdown Table
        dbc.Card([
            dbc.CardBody([
                html.Div([
                    html.H4('Forecast Snapshot', style={'color': colors['ink-strong'], 'marginBottom': '16px', 'display': 'inline-block'}),
                    dbc.Button(
                        [html.I(className='fas fa-file-excel', style={'marginRight': '8px'}), 'Export to Excel'],
                        id='export-forecast-btn',
                        color='primary',
                        outline=True,
                        size='sm',
                        style={'float': 'right'}
                    ),
                ], style={'marginBottom': '16px'}),
                html.Div(id='forecast-account-table', style={'width': '100%', 'overflowX': 'auto'}),
                dcc.Download(id='download-forecast')
            ], style={'width': '100%', 'padding': '20px'})
        ], style={'backgroundColor': colors['surface-2'], 'width': '100%'}),
    ])
