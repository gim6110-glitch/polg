"""
섹터 DB - 한국 7개 + 미국 7개
대장주 → 2등주 → 소부장(카테고리별) 세분화
동적 테마와 병행 운용
"""

SECTOR_DB = {

    # ═══════════════════════════════
    # 한국 섹터 (7개)
    # ═══════════════════════════════

    "AI반도체": {
        "description": "AI칩, HBM, 반도체 설계/제조/장비",
        "market": "KR",
        "대장주": {
            "삼성전자":  "005930",
            "SK하이닉스": "000660",
        },
        "2등주": {
            "한미반도체": "042700",
            "리노공업":   "058470",
            "ISC":        "095340",
            "HPSP":       "403870",
            "오킨스전자": "080580",
        },
        "소부장": {
            "HBM장비": {
                "한미반도체":   "042700",
                "이오테크닉스": "039030",
                "하나마이크론": "067310",
            },
            "전공정장비": {
                "원익IPS":     "240810",
                "피에스케이":  "319660",
                "주성엔지니어링": "036930",
                "테스":        "095610",
            },
            "후공정/패키징": {
                "이수페타시스": "007660",
                "심텍":        "222800",
                "대덕전자":    "008060",
            },
            "소재": {
                "솔브레인":    "357780",
                "동진쎄미켐":  "005290",
                "SK머티리얼즈": "036490",
                "후성":        "093370",
            },
            "부품/검사": {
                "HPSP":       "403870",
                "ISC":        "095340",
                "리노공업":   "058470",
                "오킨스전자": "080580",
            },
        }
    },

    "방산": {
        "description": "무기체계, 항공, 방위산업, 수출",
        "market": "KR",
        "대장주": {
            "한화에어로스페이스": "012450",
            "LIG넥스원":         "079550",
        },
        "2등주": {
            "한국항공우주": "047810",
            "현대로템":     "064350",
            "한화시스템":   "272210",
            "빅텍":         "065450",
        },
        "소부장": {
            "탄약/화약": {
                "풍산":   "103140",
                "한화":   "000880",
            },
            "전자장비": {
                "LIG넥스원": "079550",
                "빅텍":      "065450",
                "퍼스텍":    "010820",
                "이엔씨테크": "045970",
            },
            "함정/기동": {
                "한화오션":   "042660",
                "세진중공업": "075580",
                "현대로템":   "064350",
            },
            "항공부품": {
                "한국항공우주": "047810",
                "휴니드":       "005870",
                "아스트":       "067390",
            },
        }
    },

    "원전": {
        "description": "원자력 발전, SMR, 원전 수출",
        "market": "KR",
        "대장주": {
            "두산에너빌리티": "034020",
            "한전기술":       "052690",
        },
        "2등주": {
            "한전KPS":      "051600",
            "비에이치아이": "083650",
            "우진":         "105840",
            "LS ELECTRIC":  "010120",
        },
        "소부장": {
            "주기기/압력용기": {
                "두산에너빌리티": "034020",
                "비에이치아이":   "083650",
            },
            "운영/서비스": {
                "한전KPS":  "051600",
                "한전기술": "052690",
                "우진":     "105840",
            },
            "SMR/소형원전": {
                "우진":     "105840",
                "에너토크": "019990",
                "뉴보텍":   "060260",
            },
            "밸브/배관": {
                "에너토크": "019990",
                "일진파워": "094820",
            },
        }
    },

    "조선": {
        "description": "선박 제조, LNG선, 해양플랜트",
        "market": "KR",
        "대장주": {
            "HD현대중공업": "329180",
            "한화오션":     "042660",
        },
        "2등주": {
            "삼성중공업":   "010140",
            "현대미포조선": "010620",
            "HD현대":       "267250",
        },
        "소부장": {
            "기자재/부품": {
                "HD현대마린솔루션": "443060",
                "세진중공업":       "075580",
                "한국카본":         "017960",
            },
            "엔진/추진": {
                "HSD엔진":  "082740",
                "STX엔진":  "077970",
            },
            "도장/코팅": {
                "동성화인텍": "033500",
                "KC코트렐":   "119650",
            },
            "전장/자동화": {
                "HD현대일렉트릭": "267260",
                "LS ELECTRIC":    "010120",
            },
        }
    },

    "바이오": {
        "description": "제약, 바이오, CDMO, 의료기기",
        "market": "KR",
        "대장주": {
            "삼성바이오로직스": "207940",
            "셀트리온":         "068270",
        },
        "2등주": {
            "유한양행": "000100",
            "한미약품": "128940",
            "종근당":   "185750",
            "보령":     "003850",
        },
        "소부장": {
            "CDMO/위탁생산": {
                "삼성바이오로직스": "207940",
                "바이넥스":         "053030",
                "에스티팜":         "237690",
            },
            "신약/항암": {
                "유한양행":   "000100",
                "한미약품":   "128940",
                "HLB":        "028300",
                "올릭스":     "226950",
            },
            "의료기기": {
                "인바디":   "041830",
                "레이":     "228670",
                "뷰웍스":   "100120",
            },
            "AI신약": {
                "파로스아이바이오": "388870",
                "신테카바이오":     "226330",
            },
        }
    },

    "로봇": {
        "description": "산업용/협동/휴머노이드 로봇",
        "market": "KR",
        "대장주": {
            "두산로보틱스":   "454910",
            "레인보우로보틱스": "277810",
        },
        "2등주": {
            "에스피지":   "058610",
            "티로보틱스": "117730",
            "로보스타":   "090360",
        },
        "소부장": {
            "감속기/구동": {
                "에스피지":     "058610",
                "하이젠알앤엠": "239890",
                
            },
            "센서/비전": {
                
                "뷰웍스":     "100120",
            },
            "제어/SW": {
                "티로보틱스": "117730",
                "로보스타":   "090360",
            },
        }
    },

    "2차전지": {
        "description": "배터리 셀, 소재, 장비 (반등 모니터링)",
        "market": "KR",
        "대장주": {
            "LG에너지솔루션": "373220",
            "삼성SDI":        "006400",
        },
        "2등주": {
            "에코프로비엠": "247540",
            "포스코퓨처엠": "003670",
            "엘앤에프":     "066970",
        },
        "소부장": {
            "양극재": {
                "에코프로비엠": "247540",
                "코스모신소재": "005860",
                "엘앤에프":     "066970",
            },
            "음극재": {
                "대주전자재료": "078600",
                "포스코퓨처엠": "003670",
            },
            "전해질/분리막": {
                "천보":     "278280",
                "동화기업": "025900",
                "더블유씨피": "393890",
            },
            "장비": {
                "피엔티":     "137400",
                "씨아이에스": "222080",
                "하나기술":   "299030",
            },
            "검사/기타": {
                
                "코엔텍":   "029960",
            },
        }
    },

    # ═══════════════════════════════
    # 미국 섹터 (7개)
    # ═══════════════════════════════

    "미국AI": {
        "description": "AI칩, 클라우드, 데이터센터 인프라",
        "market": "US",
        "대장주": {
            "NVIDIA":    "NVDA",
            "Microsoft": "MSFT",
        },
        "2등주": {
            "AMD":        "AMD",
            "Broadcom":   "AVGO",
            "Palantir":   "PLTR",
            "CrowdStrike": "CRWD",
        },
        "소부장": {
            "전력인프라": {
                "Vistra":   "VST",
                "Eaton":    "ETN",
                "Vertiv":   "VRT",
            },
            "냉각/서버": {
                "SuperMicro": "SMCI",
                "Dell":       "DELL",
            },
            "네트워킹": {
                "Arista":  "ANET",
                "Cisco":   "CSCO",
            },
            "소프트웨어": {
                "ServiceNow": "NOW",
                "Palantir":   "PLTR",
                "Snowflake":  "SNOW",
            },
        }
    },

    "미국원전에너지": {
        "description": "원전, SMR, 천연가스, 유틸리티",
        "market": "US",
        "대장주": {
            "Vistra":        "VST",
            "Constellation": "CEG",
        },
        "2등주": {
            "Oklo":          "OKLO",
            "NextEra":       "NEE",
            "Kinder Morgan": "KMI",
        },
        "소부장": {
            "SMR/소형원전": {
                "Oklo":   "OKLO",
                "NuScale": "SMR",
            },
            "우라늄": {
                "Cameco":       "CCJ",
                "Uranium Energy": "UEC",
                "Energy Fuels": "UUUU",
            },
            "천연가스": {
                "Cheniere":  "LNG",
                "Williams":  "WMB",
                "Targa":     "TRGP",
            },
        }
    },

    "미국우주": {
        "description": "우주발사체, 위성통신, 달탐사",
        "market": "US",
        "대장주": {
            "Rocket Lab": "RKLB",
            "AST Space":  "ASTS",
        },
        "2등주": {
            "Intuitive Machines": "LUNR",
            "Satellogic":         "SATL",
        },
        "소부장": {
            "발사체": {
                "Rocket Lab": "RKLB",
            },
            "위성통신": {
                "AST SpaceMobile": "ASTS",
                "Globalstar":      "GSAT",
            },
            "달/심우주": {
                "Intuitive Machines": "LUNR",
            },
        }
    },

    "미국바이오": {
        "description": "GLP-1 비만치료제, AI신약, 바이오텍",
        "market": "US",
        "대장주": {
            "Eli Lilly": "LLY",
            "Novo Nordisk": "NVO",
        },
        "2등주": {
            "Recursion":  "RXRX",
            "Moderna":    "MRNA",
            "BioNTech":   "BNTX",
        },
        "소부장": {
            "GLP1관련": {
                "Eli Lilly":    "LLY",
                "Novo Nordisk": "NVO",
                "Viking Therapeutics": "VKTX",
            },
            "AI신약": {
                "Recursion":  "RXRX",
                
            },
            "CDMO": {
                
                "Lonza":     "LZAGY",
            },
        }
    },

    "미국방산": {
        "description": "방위산업, 항공우주, 사이버보안",
        "market": "US",
        "대장주": {
            "Lockheed Martin": "LMT",
            "RTX":             "RTX",
        },
        "2등주": {
            "Northrop Grumman": "NOC",
            "General Dynamics": "GD",
            "L3Harris":         "LHX",
        },
        "소부장": {
            "항공우주": {
                "HEICO":    "HEI",
                "TransDigm": "TDG",
            },
            "전자전/드론": {
                "Kratos":  "KTOS",
                "AeroVironment": "AVAV",
            },
            "사이버보안": {
                "CrowdStrike": "CRWD",
                "Palo Alto":   "PANW",
            },
        }
    },

    "미국양자": {
        "description": "양자컴퓨터, 양자통신",
        "market": "US",
        "대장주": {
            "IonQ": "IONQ",
            "IBM":  "IBM",
        },
        "2등주": {
            "Rigetti": "RGTI",
            "QuBit":   "QUBT",
            "D-Wave":  "QBTS",
        },
        "소부장": {
            "하드웨어": {
                "IonQ":    "IONQ",
                "Rigetti": "RGTI",
                "QuBit":   "QUBT",
                "D-Wave":  "QBTS",
            },
            "소프트웨어": {
                "IBM": "IBM",
            },
        }
    },

    "미국로봇": {
        "description": "휴머노이드, 자율주행, 물류로봇",
        "market": "US",
        "대장주": {
            "Tesla":  "TSLA",
            "Google": "GOOGL",
        },
        "2등주": {
            "Amazon": "AMZN",
            "Nvidia": "NVDA",
        },
        "소부장": {
            "센서/비전": {
                "Cognex":   "CGNX",
                "Zebra":    "ZBRA",
            },
            "액추에이터": {
                "Rockwell":  "ROK",
                "Emerson":   "EMR",
            },
            "자율주행SW": {
                "Mobileye": "MBLY",
                
            },
        }
    },
}


def get_sector_list(market=None):
    """섹터 목록 반환"""
    if market:
        return {k: v for k, v in SECTOR_DB.items() if v['market'] == market}
    return SECTOR_DB


def get_all_tickers(market=None):
    """전체 티커 목록 (소부장 카테고리 포함)"""
    tickers = {}
    for sector_name, sector_data in SECTOR_DB.items():
        if market and sector_data['market'] != market:
            continue
        for tier in ['대장주', '2등주']:
            tickers.update(sector_data.get(tier, {}))
        # 소부장 카테고리별 추가
        for cat_name, cat_stocks in sector_data.get('소부장', {}).items():
            if isinstance(cat_stocks, dict):
                tickers.update(cat_stocks)
    return tickers


def get_subsector_tickers(sector_name, category=None):
    """특정 섹터의 소부장 카테고리별 티커"""
    sector = SECTOR_DB.get(sector_name, {})
    subsectors = sector.get('소부장', {})
    if category:
        return subsectors.get(category, {})
    return subsectors


def get_sector_by_ticker(ticker):
    """티커로 섹터 찾기"""
    for sector_name, sector_data in SECTOR_DB.items():
        for tier in ['대장주', '2등주']:
            if ticker in sector_data.get(tier, {}).values():
                return sector_name, tier, None
        for cat_name, cat_stocks in sector_data.get('소부장', {}).items():
            if isinstance(cat_stocks, dict):
                if ticker in cat_stocks.values():
                    return sector_name, '소부장', cat_name
    return None, None, None


if __name__ == "__main__":
    kr = get_sector_list('KR')
    us = get_sector_list('US')
    print(f"✅ 한국 섹터: {len(kr)}개")
    for name, data in kr.items():
        subsectors = data.get('소부장', {})
        total = (len(data.get('대장주', {})) +
                 len(data.get('2등주', {})) +
                 sum(len(v) for v in subsectors.values() if isinstance(v, dict)))
        print(f"  {name}: 총 {total}개 종목 / 소부장 {len(subsectors)}개 카테고리")

    print(f"\n✅ 미국 섹터: {len(us)}개")
    for name, data in us.items():
        subsectors = data.get('소부장', {})
        total = (len(data.get('대장주', {})) +
                 len(data.get('2등주', {})) +
                 sum(len(v) for v in subsectors.values() if isinstance(v, dict)))
        print(f"  {name}: 총 {total}개 종목 / 소부장 {len(subsectors)}개 카테고리")

    print(f"\n✅ 전체 섹터: {len(SECTOR_DB)}개")

    # 티커로 섹터 찾기 테스트
    test_tickers = ["005930", "NVDA", "IONQ", "034020", "042700"]
    print("\n티커 → 섹터 매핑 테스트:")
    for t in test_tickers:
        sector, tier, cat = get_sector_by_ticker(t)
        print(f"  {t}: {sector} / {tier}" + (f" / {cat}" if cat else ""))
