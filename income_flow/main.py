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
server = app.server

app.layout = html.Div(
    [
        html.Div(
            [
                dbc.Input(
                    'symbol',
                    {
                        'margin-right': '64px',
                        'text-align': 'center',
                        'width': '140px',
                    },
                    placeholder='TSLA, 2330',
                    value='TSLA',
                ),
                dbc.Button('Plot', 'plot'),
            ],
            style={
                'display': 'flex',
                'margin-top': '64px',
            },
        ),
        dcc.Graph(
            'sankey',
            config={'displayModeBar': False},
            figure={
                'data': [go.Sankey()],
                'layout': {'paper_bgcolor': 'rgba(0, 0, 0, 0)'},
            },
            style={
                'height': '600px',
                'margin-top': '32px',
                'width': '900px',
            },
        ),
        dcc.ConfirmDialog('alert', 'Not Supported', displayed=False),
    ],
    style={
        'align-items': 'center',
        'display': 'flex',
        'flex-direction': 'column',
    },
)


@cached(43200)
def get_incomes(symbol: str) -> list[tuple[str, tuple[int, ...]]]:
    data = requests.get(
        f'https://statementdog.com/api/v2/fundamentals/{symbol}/2018/2023/cf?qbu=true&qf=analysis',
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        },
    ).json()
    q = data['quarterly']
    T = [_[1][2:4] + 'Q' + _[1][4] for _ in data['common']['TimeFiscalQ']['data'][-8:]]
    R = [int(_[1]) for _ in q['Revenue']['data'][-8:]]
    GP = [int(_[1]) for _ in q['GrossProfit']['data'][-8:]]
    CoR = [a - b for a, b in zip(R, GP)]
    OE = [int(_[1]) for _ in q['OperatingExpenses']['data'][-8:]]
    try:
        SGnA = [int(_[1]) for _ in q['SellingAndAdministrativeExpenses']['data'][-8:]]
    except (KeyError, ValueError):
        SGnA = [
            int(a[1]) + int(b[1])
            for a, b in zip(
                q['SellingExpenses']['data'][-8:],
                q['AdministrativeExpenses']['data'][-8:],
            )
        ]
    RnD = [int(_[1]) for _ in q['ResearchAndDevelopmentExpenses']['data'][-8:]]
    OI = [int(_[1]) for _ in q['OperatingIncome']['data'][-8:]]
    if not symbol[0].isdigit():
        for i, (a, b, c) in enumerate(zip(OE, SGnA, RnD)):
            if b + c > a:
                cik = requests.get(
                    f'https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={FMP_KEY}'
                ).json()[0]['cik']
                OEs = requests.get(
                    f'https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/OperatingExpenses.json',
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                    },
                ).json()['units']['USD']
                for oe in OEs:
                    if 'frame' in oe and T[i] in oe['frame']:
                        OE[i] = oe['val'] / 1e3
                        OI[i] = GP[i] - OE[i]
                        break
    return [(t, tuple(_)) for t, *_ in zip(T, CoR, GP, OE, SGnA, RnD, OI)]


@callback(
    Output('sankey', 'figure'),
    Output('alert', 'displayed'),
    Input('plot', 'n_clicks'),
    State('symbol', 'value'),
)
def plot(n_clicks: int, symbol: str):
    incomes = get_incomes(symbol)
    try:
        incomes = get_incomes(symbol)
    except (KeyError, ValueError):
        return (
            go.Figure(go.Sankey(), layout=go.Layout(paper_bgcolor='rgba(0, 0, 0, 0)')),
            True,
        )
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
                'value': [max(e, 1) / 1e3 for e in data],
            },
            name=name,
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
        for name, data in incomes
    ]
    return (
        go.Figure(
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
        ),
        False,
    )


if __name__ == '__main__':
    app.run_server(debug=True)
