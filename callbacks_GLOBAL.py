import logging
from dash import Output, Input, State

# Danielle Olenchak
# Regeneron Pharmaceuticals, Inc

# APOFIS GLOBAL CALLBACKS - Tab navigation and help modals

logger = logging.getLogger(__name__)


def register_global_callbacks(app, data):
    """Register global callbacks: tab navigation and help modals."""
    from components import create_actuals_page, create_bsb_page, create_forecast_page
    from components import create_study_forecast_tab, create_proxy_forecast_tab, create_header
    from config import get_colors

    core_df = data['core_df']
    map_df = data['map_df']

    logger.info("Registering global callbacks...")

    # ==================== UPDATE HEADER ====================
    @app.callback(
        Output('app-header', 'children'),
        Input('theme-store', 'data'))
    def update_header(theme):
        """Update header with theme colors."""
        colors = get_colors(theme)
        return create_header(colors, theme)

    # ==================== UPDATE TABS ====================
    @app.callback(
        Output('app-tabs', 'children'),
        Input('theme-store', 'data'))
    def update_tabs(theme):
        """Update tab styling based on theme."""
        import dash_bootstrap_components as dbc
        colors = get_colors(theme)
        return dbc.Tabs(
            id='tabs',
            active_tab='actuals',
            children=[
                dbc.Tab(
                    label='Home',
                    tab_id='actuals',
                    label_style={'color': colors['ink-body']},
                    active_label_style={'color': colors['brand-cyan']}
                ),
                dbc.Tab(
                    label='BSB Meter',
                    tab_id='bsb',
                    label_style={'color': colors['ink-body']},
                    active_label_style={'color': colors['brand-green']}
                ),
                dbc.Tab(
                    label='Generate Forecast',
                    tab_id='forecast',
                    label_style={'color': colors['ink-body']},
                    active_label_style={'color': colors['brand-green']}
                )
            ],
            style={'marginBottom': '20px'}
        )

    # ==================== TAB NAVIGATION ====================
    @app.callback(
        Output('tab-content', 'children'),
        [Input('tabs', 'active_tab'),
         Input('theme-store', 'data')])
    def render_tab_content(active_tab, theme):
        # Get colors for current theme
        colors = get_colors(theme)

        if active_tab == 'actuals':
            return create_actuals_page(core_df, map_df, colors)
        elif active_tab == 'bsb':
            return create_bsb_page(core_df, map_df, colors)
        elif active_tab == 'forecast':
            return create_forecast_page(core_df, map_df, colors)

    # ==================== FORECAST SUB-TAB NAVIGATION ====================
    @app.callback(
        Output('forecast-subtab-content', 'children'),
        [Input('forecast-subtabs', 'value'),
         Input('theme-store', 'data')])
    def render_forecast_subtab(subtab, theme):
        colors = get_colors(theme)
        if subtab == 'study-forecast':
            return create_study_forecast_tab(colors)
        elif subtab == 'proxy-forecast':
            return create_proxy_forecast_tab(colors)
        else:
            return create_study_forecast_tab(colors)

    # ==================== HELP MODAL CALLBACKS ====================
    @app.callback(
        Output('actuals-help-modal', 'is_open'),
        [Input('actuals-help-btn', 'n_clicks'),
         Input('actuals-help-close-btn', 'n_clicks')],
        [State('actuals-help-modal', 'is_open')])
    def toggle_actuals_help_modal(help_clicks, close_clicks, is_open):
        if help_clicks or close_clicks:
            return not is_open
        return is_open

    @app.callback(
        Output('bsb-help-modal', 'is_open'),
        [Input('bsb-help-btn', 'n_clicks'),
         Input('bsb-help-close-btn', 'n_clicks')],
        [State('bsb-help-modal', 'is_open')])
    def toggle_bsb_help_modal(help_clicks, close_clicks, is_open):
        if help_clicks or close_clicks:
            return not is_open
        return is_open

    @app.callback(
        Output('forecast-help-modal', 'is_open'),
        [Input('forecast-help-btn', 'n_clicks'),
         Input('forecast-help-close-btn', 'n_clicks')],
        [State('forecast-help-modal', 'is_open')])
    def toggle_forecast_help_modal(help_clicks, close_clicks, is_open):
        if help_clicks or close_clicks:
            return not is_open
        return is_open

    # ==================== THEME TOGGLE ====================
    @app.callback(
        Output('theme-store', 'data'),
        Input('theme-toggle', 'value'))
    def toggle_theme(toggle_value):
        """Toggle between light and dark themes."""
        if toggle_value and 'light' in toggle_value:
            return 'light'
        return 'dark'

    # ==================== UPDATE APP BACKGROUND ====================
    @app.callback(
        Output('app-container', 'style'),
        Input('theme-store', 'data'))
    def update_app_background(theme):
        """Update the main app container background based on theme."""
        colors = get_colors(theme)
        return {
            'background': f'linear-gradient(180deg, {colors["surface-0"]} 0%, {colors["surface-2"]} 100%)',
            'minHeight': '100vh'
        }

    logger.info("Global callbacks registered")
