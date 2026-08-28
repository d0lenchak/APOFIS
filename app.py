import logging
import sys
from pathlib import Path
import dash_bootstrap_components as dbc
from dash import Dash, html, dcc
from config import (
    SERVER_CONFIG,
    LOG_CONFIG,
    COLORS,
    BASE_DIR,
    validate_config)
from data_loader import load_all_data
from components import create_header
from callbacks import register_callbacks



# ==================== LOGGING SETUP ====================
def setup_logging():
    log_format = LOG_CONFIG['format']
    log_date_format = LOG_CONFIG['date_format']
    log_level = getattr(logging, LOG_CONFIG['level'].upper())
    log_file = BASE_DIR / LOG_CONFIG['file']

    # create formatter
    formatter = logging.Formatter(log_format, log_date_format)

    # console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return logging.getLogger(__name__)


# ==================== INITIALIZATION ====================
logger = setup_logging()

logger.info("="*60)
logger.info("APOFIS Dashboard Starting...")
logger.info("="*60)

# validate config
config_issues = validate_config()
if config_issues:
    logger.error("Configuration validation failed:")
    for issue in config_issues:
        logger.error(f"  - {issue}")
    logger.error("Please fix configuration issues before starting the dashboard.")
    sys.exit(1)

logger.info("Configuration validated successfully")

# get data
try:
    data = load_all_data()
    logger.info("Data loaded successfully")
except Exception as e:
    logger.error(f"Failed to load data: {e}")
    logger.error("Cannot start dashboard without data. Please check your data files.")
    sys.exit(1)


# ==================== DASH APP INITIALIZATION ====================
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    suppress_callback_exceptions=True,
    update_title=None,
    serve_locally=True)

# server for WSGI deployment (for gunicorn)
server = app.server

# ==================== APP LAYOUT ====================
app.layout = html.Div(id='app-container', style={
    'background': f'linear-gradient(180deg, {COLORS["surface-0"]} 0%, {COLORS["surface-2"]} 100%)',
    'minHeight': '100vh'
}, children=[
    dbc.Container(
        fluid=True,
        style={
            'minHeight': '100vh',
            'padding': '20px',
            'fontFamily': 'sans-serif'},

        children=[
            # HEADER - Initialize with default
            html.Div(id='app-header', children=[create_header(COLORS, 'dark')]),

            # Tab Navigation - Initialize with default
            html.Div(id='app-tabs', children=[
                dbc.Tabs(
                    id='tabs',
                    active_tab='actuals',
                    children=[
                        dbc.Tab(
                            label='Home',
                            tab_id='actuals',
                            label_style={'color': COLORS['ink-body']},
                            active_label_style={'color': COLORS['ink-body'],
                                                'fontWeight': 'bold'}
                        ),
                        dbc.Tab(
                            label='BSB Meter',
                            tab_id='bsb',
                            label_style={'color': COLORS['ink-body']},
                            active_label_style={'color': COLORS['ink-body'],
                                                                'fontWeight': 'bold'}
                        ),
                        dbc.Tab(
                            label='Forecast Studio',
                            tab_id='forecast',
                            label_style={'color': COLORS['ink-body']},
                            active_label_style={'color': COLORS['ink-body'],
                                                                'fontWeight': 'bold'}
                        )
                    ],
                    style={'marginBottom': '20px'}
                )
            ]),

            # Content area that changes based on selected tab
            html.Div(id='tab-content'),

            # Theme store for persisting light/dark mode preference
            dcc.Store(id='theme-store', storage_type='local', data='dark')
        ]
    )
])

# ==================== REGISTER CALLBACKS ====================
register_callbacks(app, data)
logger.info("Dashboard initialized successfully")


# ==================== MAIN ====================
if __name__ == '__main__':
    logger.info("="*60)
    logger.info(f"Starting APOFIS server on http://{SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    logger.info("="*60)


    app.run(
        debug=SERVER_CONFIG['debug'],
        host=SERVER_CONFIG['host'],
        port=SERVER_CONFIG['port'],
        dev_tools_hot_reload=False)
