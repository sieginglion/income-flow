import json
import os
import subprocess
from datetime import date
from typing import NamedTuple

import arrow
import dash_bootstrap_components as dbc
import dotenv
import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, callback, dcc, html
from general_cache import cached
from plotly.subplots import make_subplots

dotenv.load_dotenv()

FMP_KEY = os.environ['FMP_KEY']

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'

TRANSPARENT = 'rgba(0, 0, 0, 0)'
DARK_GREEN = '#acd58e'
DARK_RED = '#d58eac'
LIGHT_BLUE = '#8eacd5'
LIGHT_GREEN = '#c8e3b4'
LIGHT_RED = '#e3b4c8'
BAND_COLORS = ['#0077b6', '#0096C7', '#00b4d8', '#48CAE4', '#90E0EF', '#ADE8F4']


FONT_COLOR = '#7b8ab8'
FONT = dict(
    color=FONT_COLOR,
    family='Nunito,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol"',
    size=14,
)

MARGIN = '50px'

MAX_Q = 8
MAX_D = MAX_Q * 91


app = Dash(__name__, external_stylesheets=[dbc.themes.MORPH])
server = app.server

app.layout = html.Div(
    [
        html.Div(
            [
                dbc.Input(
                    'symbol',
                    {
                        'margin-right': MARGIN,
                        'text-align': 'center',
                        'width': '140px',
                    },
                    placeholder='NVDA, 2330',
                    value='TSLA',
                ),
                dbc.Button('Plot', 'plot'),
            ],
            style={
                'display': 'flex',
                'margin': MARGIN,
            },
        ),
        dcc.Graph(
            'sankey',
            config={'displayModeBar': False},
            figure={
                'data': [go.Sankey()],
                'layout': {'paper_bgcolor': TRANSPARENT},
            },
            style={
                'height': '900px',
                'width': '800px',
                'border-radius': '50px',
                'box-shadow': '5px 5px 10px rgba(55, 94, 148, 0.2), -5px -5px 10px rgba(255, 255, 255, 0.4)',
                'margin-bottom': MARGIN,
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


def get_item_from_sec(cik: str, tag: str, last_q: str):
    cmd = f'''
    curl 'https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json' \
    -H 'accept-language: en-US,en;q=0.9' \
    -H 'cache-control: no-cache' \
    -H 'user-agent: {USER_AGENT}' \
    --compressed
    '''
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    values: list[int] = []
    for e in json.loads(res.stdout)['units']['USD']:
        if 'frame' in e:
            values.append(e['val'] - (sum(values[-3:]) if e['fp'] == 'FY' else 0))
    if ('Q4' if e['fp'] == 'FY' else e['fp']) != last_q:
        values.pop()
    return pd.Series(values[-(MAX_Q + 1) :])


class Income(NamedTuple):
    d: date
    r: int
    cor: int
    gp: int
    oe: int
    oi: int
    rnd: int
    sgna: int
    eps: int


def get_incomes_from_fmp(symbol: str):
    data = requests.get(
        f'https://financialmodelingprep.com/api/v3/income-statement/{symbol}?period=quarter&limit={MAX_Q + 4}&apikey={FMP_KEY}'
    ).json()
    assert len(data)
    df = pd.DataFrame(data[::-1])
    eps = df['eps'].rolling(4).sum().dropna()
    df = df.tail(MAX_Q + 1).reset_index(drop=True)
    d = pd.to_datetime(df['fillingDate']).dt.date
    r = df['revenue']
    cik, last_q = df.iloc[-1][['cik', 'period']]
    gp = get_item_from_sec(cik, 'GrossProfit', last_q)
    oi = get_item_from_sec(cik, 'OperatingIncomeLoss', last_q)
    rnd = df['researchAndDevelopmentExpenses']
    sgna = df['sellingGeneralAndAdministrativeExpenses']
    return [Income(*_) for _ in zip(d, r, r - gp, gp, gp - oi, oi, rnd, sgna, eps)]


def get_incomes_from_sd(symbol: str):
    end = arrow.now('Asia/Taipei')
    data = requests.get(
        f'https://statementdog.com/api/v2/fundamentals/{symbol}/{end.shift(days=-(MAX_Q + 4) * 91).year}/{end.year}',
        headers={'User-Agent': USER_AGENT},
    ).json()
    assert len(data['common']['TimeCalendarQ']['data'])
    d = pd.to_datetime(
        [e for i, e in data['common']['TimeCalendarQ']['data'][-(MAX_Q + 1) :]]
    ).map(lambda x: x.date())

    def extract(item):
        return pd.Series(
            [float(e) for i, e in data['quarterly'][item]['data'][-(MAX_Q + 1) :]]
        )

    r = extract('Revenue') * 1000
    gp = extract('GrossProfit') * 1000
    oi = extract('OperatingIncome') * 1000
    rnd = extract('ResearchAndDevelopmentExpenses') * 1000
    sgna = extract('SellingExpenses') + extract('AdministrativeExpenses') * 1000
    eps = extract('EPST4Q')
    return [Income(*_) for _ in zip(d, r, r - gp, gp, gp - oi, oi, rnd, sgna, eps)]


def create_sankey_frames(incomes: list[Income]):
    incomes = incomes[-MAX_Q:]
    max_r = max(e.r for e in incomes)
    frames = [
        go.Sankey(
            hoverinfo='skip',
            link=dict(
                color=[
                    TRANSPARENT,
                    TRANSPARENT,
                    LIGHT_RED,
                    LIGHT_GREEN if income.gp > 0 else LIGHT_RED,
                    LIGHT_RED,
                    LIGHT_GREEN if income.oi > 0 else LIGHT_RED,
                    LIGHT_RED,
                    LIGHT_RED,
                ],
                source=[0, 1, 2, 2, 4, 4, 5, 5],
                target=[1, 2, 3, 4, 5, 6, 7, 8],
                value=[
                    (abs(e) + 1) / 1e6
                    for e in (
                        max_r,
                        income.r,
                        income.cor,
                        income.gp,
                        income.oe,
                        income.oi,
                        income.rnd,
                        income.sgna,
                    )
                ],
            ),
            name=income.d.strftime('%y-%m-%d'),
            node=dict(
                color=[
                    TRANSPARENT,
                    TRANSPARENT,
                    DARK_GREEN,
                    DARK_RED,
                    DARK_GREEN if income.gp > 0 else DARK_RED,
                    DARK_RED,
                    DARK_GREEN if income.oi > 0 else DARK_RED,
                    DARK_RED,
                    DARK_RED,
                ],
                label=[
                    '',
                    '',
                    f'Revenue: {income.r // 1e6:,.0f}M',
                    f'Cost of Revenue: {income.cor // 1e6:,.0f}M',
                    f'Gross Profit: {income.gp // 1e6:,.0f}M',
                    f'Operating Expenses: {income.oe // 1e6:,.0f}M',
                    f'Operating Income: {income.oi // 1e6:,.0f}M',
                    f'R&D: {income.rnd // 1e6:,.0f}M',
                    f'SG&A: {income.sgna // 1e6:,.0f}M',
                ],
                line={'width': 0},
                x=[-0.67, -0.33, 0.01, 0.33, 0.33, 0.67, 0.67, 1.0, 1.0],
                y=[0.64, 0.64, 0.64, 1.0, 0.29, 0.57, 0.01, 0.34, 0.8],
            ),
        )
        for income in incomes + [incomes[-1]]
    ]
    frames[-1].name = 'Today'
    return frames


def get_prices(symbol: str):
    market = 'u' if symbol[0].isalpha() else 't'
    prices = requests.get(
        f'http://52.198.155.160:8080/prices?market={market}&symbol={symbol}&n={MAX_D}'
    ).json()
    now = arrow.now('Etc/GMT+5' if market == 'u' else 'Asia/Taipei')
    dates = [
        e.date()
        for e in pd.date_range(now.shift(days=-(len(prices) - 1)).date(), now.date())
    ]
    return pd.Series(prices, dates)


def calc_bands(incomes: list[Income], prices: pd.Series):
    dates = [e.date() for e in pd.date_range(incomes[0].d, prices.index[-1])]
    eps = (
        pd.Series({income.d: income.eps for income in incomes}, index=dates)
        .ffill()
        .tail(MAX_D)
    )
    eps[eps <= 0] = None
    PE = prices / eps
    min_pe, max_pe = PE.min(), PE.max()
    if not min_pe < max_pe:
        return pd.DataFrame()
    bands = pd.DataFrame(index=eps.index)
    for p in range(0, 120, 20):
        pe = min_pe + (max_pe - min_pe) * (p / 100)
        bands[pe] = eps * pe
    return bands


def create_price_frames_and_bands(symbol, incomes):
    prices = get_prices(symbol)
    dates = [e.d for e in incomes[-MAX_Q:]] + [prices.index[-1]]
    frames = [
        go.Scatter(
            hoverlabel=dict(
                align='right', bgcolor='white', bordercolor='white', font=FONT
            ),
            hovertemplate='%{x|%y-%m-%d}<br>%{y:.2f}<extra></extra>',
            line=dict(color=LIGHT_BLUE, shape='spline', width=4),
            mode='lines',
            x=prices.index,
            y=prices.loc[: d + pd.Timedelta(days=1)],
        )
        for d in dates
    ]
    band_df = calc_bands(incomes, prices).fillna(0)
    bands = [
        go.Scatter(
            fill='tonexty' if i else None,
            hoverinfo='skip',
            line=dict(color=BAND_COLORS[i], width=0),
            mode='lines',
            name=round(pe),
            x=band_df.index,
            y=band,
        )
        for i, (pe, band) in enumerate(band_df.items())
    ]
    return frames, bands


@callback(
    Output('sankey', 'figure'),
    Output('alert', 'displayed'),
    State('symbol', 'value'),
    Input('plot', 'n_clicks'),
)
def plot(symbol: str, n_clicks: int):
    try:
        incomes = (
            get_incomes_from_fmp(symbol)
            if symbol[0].isalpha()
            else get_incomes_from_sd(symbol)
        )
    except (AssertionError, KeyError, ValueError):
        return go.Figure(go.Sankey(), go.Layout(paper_bgcolor=TRANSPARENT)), True
    s_frames = create_sankey_frames(incomes)
    p_frames, bands = create_price_frames_and_bands(symbol, incomes)
    fig = make_subplots(
        2, 1, specs=[[{'type': 'sankey'}], [{'type': 'xy'}]], vertical_spacing=0.2
    )
    fig.add_trace(s_frames[-1], 1, 1)
    fig.add_trace(p_frames[-1], 2, 1)
    for band in bands:
        fig.add_trace(band, 2, 1)
        fig.add_annotation(
            showarrow=False, text=band.name + 'X', x=band.x[-1], y=band.y[-1]
        )
    fig.frames = [
        go.Frame(data=[s_frame, p_frame], name=s_frame.name)
        for s_frame, p_frame in zip(s_frames, p_frames)
    ]
    fig.update_layout(
        dict(
            font=FONT,
            paper_bgcolor=TRANSPARENT,
            plot_bgcolor=TRANSPARENT,
            showlegend=False,
            sliders=[
                dict(
                    borderwidth=0,
                    currentvalue={'visible': False},
                    len=0.9,
                    pad={'b': 20},
                    steps=[
                        dict(
                            args=[
                                [s_frame.name],
                                dict(mode='immediate', transition={'duration': 0}),
                            ],
                            label=s_frame.name,
                            method='animate',
                        )
                        for s_frame in s_frames
                    ],
                    tickcolor=FONT_COLOR,
                    x=0.1,
                )
            ],
            updatemenus=[
                dict(
                    bgcolor='white',
                    borderwidth=0,
                    buttons=[
                        dict(
                            args=[
                                None,
                                dict(
                                    frame={'duration': 1500},
                                    fromcurrent=True,
                                    transition={'duration': 0},
                                ),
                            ],
                            label='⏵',
                            method='animate',
                        ),
                        dict(
                            args=[[None], dict(mode='immediate')],
                            label='⏸',
                            method='animate',
                        ),
                    ],
                    direction='right',
                    font={'family': 'sans-serif'},
                    showactive=False,
                    type='buttons',
                    x=0.07,
                    y=-0.02,
                )
            ],
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
        )
    )
    return fig, False


if __name__ == '__main__':
    app.run_server(debug=True)
