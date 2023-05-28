import re
from dataclasses import asdict
from random import randint
from time import sleep
from typing import Any, Dict, List, Iterable

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from mimesis import Generic, Locale
from tqdm import tqdm

from transfermarkt_analysis.crawl.consts import BASE_URL, DATA_DIR, URLS_DIR
from transfermarkt_analysis.crawl.structs import (
    MatchGoal,
    MatchSubstitute,
    MatchCard,
    MatchStatistics,
    Match,
)


provider: Generic = Generic(locale=Locale.EN)


def get_headers() -> Dict[str, Any]:
    headers: Dict[str, Any] = {"User-Agent": provider.internet.user_agent()}
    return headers


def make_request(url: str) -> requests.Response:
    headers: Dict[str, Any] = get_headers()
    try:
        resp: requests.Response = requests.get(
            url=url,
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException:
        return None


def obj_id(url: str) -> str:
    pattern: str = r"\d+"
    mtch: str = re.search(pattern, url).group()
    return mtch


def result_validator(tag: Tag) -> str:
    pattern: str = r"\d+\:\d+"
    mtch: str = re.search(pattern, tag.get_text()).group()
    return mtch


def matchday_validator(tag: Tag) -> str:
    pattern: str = r"\d+"
    mtch: str = re.search(pattern, tag.get_text()).group()
    return mtch


def match_date_validator(tag: Tag) -> str:
    pattern: str = r"\d+\.\d+\.\d+"
    mtch: str = re.search(pattern, tag.get_text()).group()
    return mtch


def goal_type_validator(tag: Tag) -> str:
    pattern: str = r",|\n"
    mtchs: str = re.split(pattern, tag.get_text())
    return mtchs[2].strip()


def goals_extractor(match_id: str, tag: Tag) -> MatchGoal:
    selectors: Dict[str, str] = {
        "scorrer": "div.sb-aktion div.sb-aktion-aktion a.wichtig",
        "assist": "div.sb-aktion div.sb-aktion-aktion a.wichtig",
        "goal_type": "div.sb-aktion div.sb-aktion-aktion",
    }
    scorrer: Tag = None
    assist: Tag = None
    try:
        scorrer = tag.select(selectors["scorrer"], href=True)[0]
        assist = tag.select(selectors["assist"], href=True)[1]
    except Exception:
        pass

    return MatchGoal(
        match_id=match_id,
        scorrer_id=obj_id(scorrer["href"]) if scorrer else None,
        scorrer=scorrer.get_text() if scorrer else None,
        goal_type=goal_type_validator(tag.select_one(selectors["goal_type"])),
        assist_id=obj_id(assist["href"]) if assist else None,
        assist=assist.get_text() if assist else None,
    )


def subtitate_extractor(match_id: str, tag: Tag) -> MatchSubstitute:
    selectors: Dict[str, str] = {
        "player_in": "div.sb-aktion div.sb-aktion-aktion span.sb-aktion-wechsel-ein a.wichtig",
        "player_out": "div.sb-aktion div.sb-aktion-aktion span.sb-aktion-wechsel-aus a.wichtig",
    }

    player_in: Tag = None
    player_out: Tag = None
    try:
        player_in = tag.select_one(selectors["player_in"], href=True)
        player_out = tag.select_one(selectors["player_out"], href=True)
    except Exception:
        pass

    return MatchSubstitute(
        match_id=match_id,
        player_in_id=obj_id(player_in["href"]) if player_in else None,
        player_in=player_in.get_text() if player_in else None,
        player_out_id=obj_id(player_out["href"]) if player_out else None,
        player_out=player_out.get_text() if player_out else None,
    )


def card_extractor(match_id: str, tag: Tag) -> MatchCard:
    selectors: Dict[str, str] = {
        "player": "div.sb-aktion div.sb-aktion-aktion a.wichtig",
        "yellow_card": "div.sb-aktion div.sb-aktion-spielstand span.sb-sprite.sb-gelb",
        "yellow_red_card": "div.sb-aktion-spielstand span.sb-sprite.sb-gelbrot",
        "red_card": "div.sb-aktion div.sb-aktion-spielstand span.sb-sprite.sb-rot",
    }

    player: Tag = None
    yellow_card: Tag = None
    yellow_red_card: Tag = None
    red_card: Tag = None

    try:
        player = tag.select_one(selectors["player"], href=True)
        yellow_card = tag.select_one(selectors["yellow_card"])
        yellow_red_card = tag.select_one(selectors["yellow_red_card"])
        red_card = tag.select_one(selectors["red_card"])
    except Exception:
        pass

    match_card: MatchCard = MatchCard(
        match_id=match_id,
        player_id=obj_id(player["href"]),
        player=player.get_text(),
    )

    if yellow_card:
        match_card.card = "yellow"
    elif yellow_red_card:
        match_card.card = "yellow-red"
    elif red_card:
        match_card.card = "red"

    return match_card


def statistics_extractor(tag: Tag) -> MatchStatistics:
    url: str = BASE_URL + tag["href"]
    resp: requests.Response = make_request(url)
    counter: int = 0
    
    while counter <= 5 and resp is None:
        resp = make_request(url)
        counter += 1

    if resp:
        if resp.status_code == 200:
            soup: BeautifulSoup = BeautifulSoup(markup=resp.text, features="html.parser")
            selectors: Dict[str, Any] = {
                "home": "div.box div.sb-statistik ul li.sb-statistik-heim div div.sb-statistik-zahl",
                "away": "div.box div.sb-statistik ul li.sb-statistik-gast div div.sb-statistik-zahl",
            }
            return MatchStatistics(
                home_total_shots=soup.select(selectors["home"])[0].get_text(),
                away_total_shots=soup.select(selectors["away"])[0].get_text(),
                home_shots_off_target=soup.select(selectors["home"])[1].get_text(),
                away_shots_off_target=soup.select(selectors["away"])[1].get_text(),
                home_shots_saved=soup.select(selectors["home"])[2].get_text(),
                away_shots_saved=soup.select(selectors["away"])[2].get_text(),
                home_corners=soup.select(selectors["home"])[3].get_text(),
                away_corners=soup.select(selectors["away"])[3].get_text(),
                home_freekicks=soup.select(selectors["home"])[4].get_text(),
                away_freekicks=soup.select(selectors["away"])[4].get_text(),
                home_fouls=soup.select(selectors["home"])[5].get_text(),
                away_fouls=soup.select(selectors["away"])[5].get_text(),
                home_offsides=soup.select(selectors["home"])[6].get_text(),
                away_offsides=soup.select(selectors["away"])[6].get_text(),
            )
    return MatchStatistics()


def match_extractor(resp: requests.Response) -> Match:
    soup: BeautifulSoup = BeautifulSoup(markup=resp.text, features="html.parser")
    selectors: Dict[str, str] = {
        "home_team": "div.box.sb-spielbericht-head div.box-content div.sb-team.sb-heim a.sb-vereinslink",
        "away_team": "div.box.sb-spielbericht-head div.box-content div.sb-team.sb-gast a.sb-vereinslink",
        "result": "div.sb-spieldaten div.ergebnis-wrap div.sb-ergebnis div.sb-endstand",
        "matchday": "div.box.sb-spielbericht-head div.box-content div.sb-spieldaten p.sb-datum.hide-for-small a:nth-child(1)",
        "match_date": "div.box.sb-spielbericht-head div.box-content div.sb-spieldaten p.sb-datum.hide-for-small a:nth-child(2)",
        "home_goals": "div.box div#sb-tore.sb-ereignisse ul li.sb-aktion-heim",
        "away_goals": "div.box div#sb-tore.sb-ereignisse ul li.sb-aktion-gast",
        "home_substitutions": "div.box div#sb-wechsel.sb-ereignisse ul li.sb-aktion-heim",
        "away_substitutions": "div.box div#sb-wechsel.sb-ereignisse ul li.sb-aktion-gast",
        "home_cards": "div.box div#sb-karten.sb-ereignisse ul li.sb-aktion-heim",
        "away_cards": "div.box div#sb-karten.sb-ereignisse ul li.sb-aktion-gast",
        "statistics": "li#statistik a.tm-subnav-item.megamenu",
    }
    match_id: str = obj_id(resp.url)
    home_team: Tag = soup.select_one(selectors["home_team"], href=True)
    away_team: Tag = soup.select_one(selectors["away_team"], href=True)
    return Match(
        match_id=match_id,
        home_team_id=obj_id(home_team["href"]),
        home_team=home_team.get_text(),
        away_team_id=obj_id(away_team["href"]),
        away_team=away_team.get_text(),
        result=result_validator(soup.select_one(selectors["result"])),
        matchday=matchday_validator(soup.select_one(selectors["matchday"])),
        match_date=match_date_validator(soup.select_one(selectors["match_date"])),
        home_goals=[
            goals_extractor(match_id, tag) for tag in soup.select(selectors["home_goals"])
        ],
        away_goals=[
            goals_extractor(match_id, tag) for tag in soup.select(selectors["away_goals"])
        ],
        home_substitutions=[
            subtitate_extractor(match_id, tag)
            for tag in soup.select(selectors["home_substitutions"])
        ],
        away_substitutions=[
            subtitate_extractor(match_id, tag)
            for tag in soup.select(selectors["away_substitutions"])
        ],
        home_cards=[
            card_extractor(match_id, tag) for tag in soup.select(selectors["home_cards"])
        ],
        away_cards=[
            card_extractor(match_id, tag) for tag in soup.select(selectors["away_cards"])
        ],
        statistics=statistics_extractor(
            soup.select_one(selectors["statistics"], href=True)
        ),
    )


def get_matchday_urls_df(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    output_df: pd.DataFrame = pd.read_csv(DATA_DIR / f"matches/{filename}.csv")
    return df.loc[~np.isin(df.index.values, output_df.loc[:, "url_id"])]


def match_writer(url_id: int, resp: requests.Request, filename: str) -> None:
    match_data: Dict[str, Any] = {"url_id": url_id, **asdict(match_extractor(resp))}
    match_df: pd.DataFrame = pd.DataFrame(
        [
            match_data,
        ]
    )
    match_df.to_csv(DATA_DIR / f"matches/{filename}.csv", mode="a", index=False, header=False)


def match_crawl(df: pd.DataFrame, filename: str) -> None:
    counter: int = 0
    index_list: Iterable = iter(df.index.values.tolist())
    url_list: Iterable = iter(df["url"].tolist())
    for url_id, url in tqdm(zip(index_list, url_list)):
        # url_id = i
        print(f"getting {url_id} {url}")

        resp: requests.Response = make_request(url)

        while resp is None or resp.status_code != 200:
            url_id = next(index_list)
            url = next(url_list)
            print(f"getting instead {url_id} {url}")
            resp = make_request(url)

        if resp is not None:
            if resp.status_code == 200:
                match_writer(url_id, resp, filename)
                print(f"{resp.status_code} got {url_id} {url}")
                counter += 1                

        if counter % 50 == 0:
            counter = 0
            sleep(30)


def match_partion_writer(filename: str, start: int, end: int) -> None:
    df: pd.DataFrame = pd.read_csv(URLS_DIR / "match_urls.csv").iloc[start:end,]
    match_crawl(get_matchday_urls_df(df, filename), filename)