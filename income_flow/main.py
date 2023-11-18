import os

import dash_bootstrap_components as dbc
import dotenv
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, callback, dcc, html

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
def plot_sankey(n_clicks, symbol):
    sankeys = [
        go.Sankey(
            name=I[0],
            node={
                'label': [
                    'Revenue',
                    'Cost of Revenue',
                    'Gross Profit',
                    'Operating Expenses',
                    'SG&A',
                    'R&D',
                    'Oerating Income',
                ],
                'x': [0.01, 0.33, 0.33, 0.67, 1.00, 1.00, 0.67],
                'y': [0.55, 0.90, 0.20, 0.47, 0.67, 0.27, 0.01],
                'pad': 32,
                'color': [
                    '#00cf9d',
                    '#ff3062',
                    '#00cf9d',
                    '#ff3062',
                    '#ff3062',
                    '#ff3062',
                    '#00cf9d',
                ],
                'line': {'width': 0},
                'hoverinfo': 'none',
            },
            link={
                'source': [0, 0, 2, 3, 3, 2],
                'target': [1, 2, 3, 4, 5, 6],
                'value': [e // 1e6 for e in I[1]],
                'color': [
                    '#f289a2',
                    '#1de6b5',
                    '#f289a2',
                    '#f289a2',
                    '#f289a2',
                    '#1de6b5',
                ],
                'hovertemplate': '%{target.label}: %{value}<extra></extra>',
                'hoverlabel': {'bordercolor': 'white'},
            },
            arrangement='fixed',
            valueformat='$,',
            valuesuffix='M',
        )
        for I in get_incomes(symbol)
    ]
    fig = go.Figure(
        data=sankeys[0],
        frames=[go.Frame(data=sankey, name=str(k)) for k, sankey in enumerate(sankeys)],
        layout=go.Layout(
            updatemenus=[
                dict(
                    type="buttons",
                    buttons=[
                        {
                            'label': '⏵',
                            'method': 'animate',
                            'args': [
                                None,
                                {
                                    'frame': {'duration': 1000, 'redraw': True},
                                    'mode': 'immediate',
                                },
                            ],
                        },
                        {
                            "args": [
                                [None],
                                {
                                    "frame": {"duration": 0, "redraw": False},
                                    "mode": "immediate",
                                },
                            ],
                            "label": "⏸",
                            "method": "animate",
                        },
                    ],
                    y=0,
                    x=0.07,
                    pad=dict(b=10, t=67),
                    direction='right',
                )
            ],
            sliders=[
                dict(
                    active=0,
                    currentvalue=dict(
                        font=dict(size=12),
                        visible=True,
                        xanchor="right",
                    ),
                    transition=dict(duration=300),
                    pad=dict(b=10, t=50),
                    len=0.9,
                    x=0.1,
                    y=0,
                    steps=[
                        dict(
                            label=sankeys[i].name,
                            method="animate",
                            args=[
                                [str(i)],
                                {
                                    "frame": {"duration": 1000, "redraw": True},
                                    "mode": "immediate",
                                    "transition": {"duration": 300},
                                },
                            ],
                        )
                        for i in range(len(sankeys))
                    ],
                )
            ],
        ),
    )

    fig.update_layout(plot_bgcolor='rgba(0, 0, 0, 0)', paper_bgcolor='rgba(0, 0, 0, 0)')

    return fig


if __name__ == '__main__':
    app.run_server(debug=True)
