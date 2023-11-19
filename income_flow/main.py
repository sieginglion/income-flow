import os

import dash_bootstrap_components as dbc
import dotenv
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, callback, dcc, html
from general_cache import cached

dotenv.load_dotenv()


FMP_KEY = os.getenv('FMP_KEY')


app = Dash(__name__, external_stylesheets=[dbc.themes.MORPH])

app.layout = html.Div(
    [
        html.Div(
            [
                dbc.Input(
                    id='symbol',  # Assigning an ID to the input
                    value='AAPL',
                    style={
                        'margin-right': '64px',
                        'text-align': 'center',
                        'width': '128px',
                    },
                ),
                dbc.Button('Plot', id='plot'),  # Assigning an ID to the button
            ],
            style={'display': 'flex', 'margin-bottom': '32px'},
        ),
        dcc.Graph(
            id='sankey',
            style={'width': '900px', 'height': '600px', 'margin-bottom': '64px'},
            figure={
                'data': [],
                'layout': {
                    'xaxis': {'visible': False},
                    'yaxis': {'visible': False},
                    'annotations': [
                        {
                            'text': 'Loading...',
                            'xref': 'paper',
                            'yref': 'paper',
                            'showarrow': False,
                            'font': {'size': 28},
                        }
                    ],
                    'paper_bgcolor': 'rgba(0, 0, 0, 0)',
                    'plot_bgcolor': 'rgba(0, 0, 0, 0)',
                },
            },
            config={'displayModeBar': False}
            # loading_state={'is_loading': True},
        ),  # Assigning an ID to the chart
    ],
    style={
        'align-items': 'center',
        'display': 'flex',
        'flex-direction': 'column',
        'margin': '64px',
    },
)


@cached(43200)
def get_incomes(symbol: str) -> list[tuple[str, tuple[int, ...]]]:
    res = requests.get(
        f'https://financialmodelingprep.com/api/v3/income-statement/{symbol}?period=quarter&limit=8&apikey={FMP_KEY}'
    )
    return [
        (
            e['calendarYear'][-2:] + e['period'],
            (
                e['costOfRevenue'],
                e['grossProfit'],
                e['operatingExpenses'],
                e['sellingGeneralAndAdministrativeExpenses'],
                e['researchAndDevelopmentExpenses'],
                e['operatingIncome'],
            ),
        )
        for e in reversed(res.json())
    ]


@callback(
    Output('sankey', 'figure'),
    Input('plot', 'n_clicks'),
    State('symbol', 'value'),
)
def plot_sankey(n_clicks: int, symbol: str):
    sankeys = [
        go.Sankey(
            link={
                'color': [
                    '#f289a2',
                    '#1de6b5',
                    '#f289a2',
                    '#f289a2',
                    '#f289a2',
                    '#1de6b5',
                ],
                'hovertemplate': '%{target.label}: %{value}<extra></extra>',
                'source': [0, 0, 2, 3, 3, 2],
                'target': [1, 2, 3, 4, 5, 6],
                'value': [max(e, 1) / 1e6 for e in v],
            },
            name=k,
            node={
                'color': [
                    '#00cf9d',
                    '#ff3062',
                    '#00cf9d',
                    '#ff3062',
                    '#ff3062',
                    '#ff3062',
                    '#00cf9d',
                ],
                'hoverinfo': 'none',
                'label': [
                    'Revenue',
                    'Cost of Revenue',
                    'Gross Profit',
                    'Operating Expenses',
                    'SG&A',
                    'R&D',
                    'Oerating Income',
                ],
                'line': {'width': 0},
                'pad': 32,
                'x': [0.01, 0.33, 0.33, 0.67, 1.00, 1.00, 0.67],
                'y': [0.61, 0.94, 0.27, 0.53, 0.75, 0.32, 0.01],
            },
            valueformat=',.0f',
            valuesuffix='M',
        )
        for k, v in get_incomes(symbol)
    ]
    return go.Figure(
        sankeys[0],
        go.Layout(
            sliders=[
                {
                    'currentvalue': {'visible': False},
                    'len': 0.9,
                    'steps': [
                        {
                            'args': [[sankey.name], {'mode': 'immediate'}],
                            'label': sankey.name,
                            'method': 'animate',
                        }
                        for sankey in sankeys
                    ],
                    'x': 0.1,
                    'y': -0.25,
                }
            ],
            updatemenus=[
                {
                    'buttons': [
                        {
                            'args': [
                                None,
                                {'frame': {'duration': 1000}, 'fromcurrent': True},
                            ],
                            'label': '⏵',
                            'method': 'animate',
                        },
                        {
                            'args': [[None], {'mode': 'immediate'}],
                            'label': '⏸',
                            'method': 'animate',
                        },
                    ],
                    'direction': 'right',
                    'type': 'buttons',
                    'x': 0.08,
                    'y': -0.285,
                }
            ],
            paper_bgcolor='rgba(0, 0, 0, 0)',
        ),
        [go.Frame(data=sankey, name=sankey.name) for sankey in sankeys],
    )


if __name__ == '__main__':
    app.run_server(debug=True)
