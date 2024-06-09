import datetime
import json
import os
import subprocess
from typing import NamedTuple

import arrow
import dash_bootstrap_components as dbc
import dotenv
import pandas as pd
import requests as rq
from dash import Dash, Input, Output, State, callback, dcc, html
from general_cache import cached
from plotly import graph_objects as go
from plotly.subplots import make_subplots

dotenv.load_dotenv()

FMP_KEY = os.environ['FMP_KEY']
MAX_Q = 8
MAX_D = MAX_Q * 91
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'

MARGIN = '50px'
FONT_COLOR = '#7b8ab8'
FONT = dict(
    color=FONT_COLOR,
    family='Nunito,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol"',
    size=14,
)

BAND_COLORS = ['#0077b6', '#0096C7', '#00b4d8', '#48CAE4', '#90E0EF', '#ADE8F4']
BLUE = '#8eacd5'
DARK_GREEN = '#acd58e'
DARK_RED = '#d58eac'
LIGHT_GREEN = '#c8e3b4'
LIGHT_RED = '#e3b4c8'
TRANSPARENT = 'rgba(0, 0, 0, 0)'

app = Dash(__name__, external_stylesheets=[dbc.themes.MORPH])
server = app.server

app.layout = html.Div(
    [
        html.Div(
            [
                dbc.Input(
                    'input',
                    dict(textAlign='center', width='140px'),
                    placeholder='TSLA, 2330',
                    value='TSLA',
                ),
                dbc.Button('Plot', 'button', style=dict(marginLeft=MARGIN)),
            ],
            style=dict(display='flex', marginTop=MARGIN),
        ),
        dcc.Graph(
            'graph',
            config=dict(displayModeBar=False),
            figure=dict(data=[go.Sankey()], layout=dict(paper_bgcolor=TRANSPARENT)),
            style=dict(
                borderRadius='50px',
                boxShadow='5px 5px 10px rgba(55, 94, 148, 0.2), -5px -5px 10px rgba(255, 255, 255, 0.4)',
                height='880px',
                marginTop=MARGIN,
                width='800px',
            ),
        ),
        dcc.ConfirmDialog('alert', 'Not Supported', displayed=False),
    ],
    style=dict(
        alignItems='center',
        display='flex',
        flexDirection='column',
        paddingBottom=MARGIN,
    ),
)


class NotSupported(Exception): ...


def get_item_from_sec(cik: str, tag: str, filing_dates: pd.Series):
    cmd = f'''
    curl 'https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json' \
    -H 'accept-language: en-US,en;q=0.9' \
    -H 'cache-control: no-cache' \
    -H 'user-agent: {USER_AGENT}' \
    --compressed
    '''
    res = subprocess.run(cmd, capture_output=True, shell=True, text=True)
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise NotSupported
    df = pd.DataFrame(data['units']['USD'])
    df = df[df['form'].isin(['10-Q', '10-K']) & df['frame'].notna()].reset_index(
        drop=True
    )
    for i in df[df['form'] == '10-K'].index:
        if ((q := df.loc[i - 3 : i - 1])['form'] == '10-Q').sum() == 3:
            df.at[i, 'val'] -= q['val'].sum()
        else:
            df = df.drop(i)

    def find_filing_date(end_date: datetime.date):
        result = filing_dates[
            (end_date < filing_dates)
            & (filing_dates < end_date + pd.Timedelta(days=91))
        ]
        return result.iloc[0] if len(result) else pd.NA

    df['filing_date'] = pd.to_datetime(df['end']).dt.date.map(find_filing_date)
    df = df.set_index('filing_date')
    try:
        s = df.loc[filing_dates, 'val']
    except KeyError:
        raise NotSupported
    return s.reset_index(drop=True)


class Income(NamedTuple):
    d: datetime.date
    r: int
    cor: int
    gp: int
    oe: int
    oi: int
    rnd: int
    sgna: int
    eps: int


def get_incomes_from_fmp(symbol: str):
    data = rq.get(
        f'https://financialmodelingprep.com/api/v3/income-statement/{symbol}?period=quarter&limit={MAX_Q + 4}&apikey={FMP_KEY}'
    ).json()
    if len(data) != MAX_Q + 4:
        raise NotSupported
    df = pd.DataFrame(data[::-1])
    eps = df['eps'].rolling(4).sum().loc[3:]
    df = df.loc[3:].reset_index(drop=True)
    d = pd.to_datetime(df['fillingDate']).dt.date
    r = df['revenue']
    cik = df.loc[0, 'cik']
    gp = get_item_from_sec(cik, 'GrossProfit', d)
    oi = get_item_from_sec(cik, 'OperatingIncomeLoss', d)
    rnd = df['researchAndDevelopmentExpenses']
    sgna = df['sellingGeneralAndAdministrativeExpenses']
    return [Income(*_) for _ in zip(d, r, r - gp, gp, gp - oi, oi, rnd, sgna, eps)]


def get_incomes_from_dog(symbol: str):
    end = arrow.now('Asia/Taipei')
    data = rq.get(
        f'https://statementdog.com/api/v2/fundamentals/{symbol}/{end.shift(days=-(MAX_Q + 4) * 91).year}/{end.year}',
        headers={'User-Agent': USER_AGENT},
    ).json()
    if len(data['common']['TimeCalendarQ']['data']) < MAX_Q + 4:
        raise NotSupported
    fmp_data = rq.get(
        f'https://financialmodelingprep.com/api/v3/income-statement/{symbol}?period=quarter&limit={MAX_Q + 1}&apikey={FMP_KEY}'
    ).json()
    fmp_df = pd.DataFrame(fmp_data[::-1])
    d = pd.to_datetime(fmp_df['fillingDate']).dt.date

    def extract(item):
        try:
            return pd.Series(
                [float(e) for i, e in data['quarterly'][item]['data'][-(MAX_Q + 1) :]]
            )
        except (KeyError, ValueError):
            raise NotSupported

    r = extract('Revenue') * 1000
    gp = extract('GrossProfit') * 1000
    oi = extract('OperatingIncome') * 1000
    rnd = extract('ResearchAndDevelopmentExpenses') * 1000
    try:
        sgna = extract('SellingAndAdministrativeExpenses') * 1000
    except NotSupported:
        sgna = extract('SellingExpenses') + extract('AdministrativeExpenses') * 1000
    eps = extract('EPST4Q')
    return [Income(*_) for _ in zip(d, r, r - gp, gp, gp - oi, oi, rnd, sgna, eps)]


# @cached(43200)
def get_incomes(symbol):
    funcs = (
        [get_incomes_from_fmp, get_incomes_from_dog]
        if symbol[0].isalpha()
        else [get_incomes_from_dog]
    )
    for func in funcs:
        try:
            return func(symbol)
        except NotSupported:
            continue


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
    prices = rq.get(
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
        pd.Series({income.d: income.eps for income in incomes}, dates)
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
            line=dict(color=BLUE, shape='spline', width=4),
            mode='lines',
            x=prices.index,
            y=prices.loc[: d + pd.Timedelta(days=7)],
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
    Output('graph', 'figure'),
    Output('alert', 'displayed'),
    State('input', 'value'),
    Input('button', 'n_clicks'),
)
def main(symbol: str, n_clicks: int):
    if not (incomes := get_incomes(symbol)):
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
            showarrow=False, text=band.name + 'x', x=band.x[-1], y=band.y[-1]
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
                    len=0.92,
                    pad={'b': 40},
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
                    x=0.12,
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
                                    frame={'duration': 2000},
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
                    x=0.09,
                    y=-0.02,
                )
            ],
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
        )
    )
    return fig, False


if __name__ == '__main__':
    app.run(debug=True)
