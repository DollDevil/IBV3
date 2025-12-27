from __future__ import annotations
import random
import discord

STYLE_1 = {
    "confident_smirk": [
        "https://i.imgur.com/5nsuuCV.png",
        "https://i.imgur.com/8qQkq0p.png",
        "https://i.imgur.com/8AsaLI5.png",
        "https://i.imgur.com/sGDoIDA.png",
        "https://i.imgur.com/qC0MOZN.png",
        "https://i.imgur.com/rcgIEtj.png",
    ],
    "bothered": ["https://i.imgur.com/k7AexFe.png"],
    "laughing": [
        "https://i.imgur.com/eoNSHQ1.png",
        "https://i.imgur.com/TS1KMQe.png",
        "https://i.imgur.com/zcb1ztK.png",
        "https://i.imgur.com/lpMQlWO.png",
    ],
    "displeased": [
        "https://i.imgur.com/9g4g7iV.png",
        "https://i.imgur.com/h68lq5E.png",
        "https://i.imgur.com/0pFNbQc.png",
        "https://i.imgur.com/8Ay5met.png",
        "https://i.imgur.com/ZQQIji3.png",
        "https://i.imgur.com/KmAneUM.png",
        "https://i.imgur.com/9oUjOQQ.png",
    ],
    "pleased": [
        "https://i.imgur.com/sCjhY7W.png",
        "https://i.imgur.com/0BM3E8t.png",
        "https://i.imgur.com/qTvUqq6.png",
        "https://i.imgur.com/JAXB48Q.png",
        "https://i.imgur.com/W3uzVdO.png",
    ],
    "soft_smirk": [
        "https://i.imgur.com/qC0MOZN.png",
        "https://i.imgur.com/rcgIEtj.png",
        "https://i.imgur.com/8qQkq0p.png",
    ],
    "neutral": ["https://i.imgur.com/9oUjOQQ.png"],
}

STYLE_2 = {
    "blue": [
        "https://i.imgur.com/fzk4mNv.png",
        "https://i.imgur.com/GZlj07G.png",
        "https://i.imgur.com/RGs0Igy.png",
        "https://i.imgur.com/5lChRC4.png",
        "https://i.imgur.com/DiUpVdA.png",
        "https://i.imgur.com/iF3oM08.png",
        "https://i.imgur.com/7LAxXuZ.png",
        "https://i.imgur.com/vnlOeXI.png",
    ],
    "red": [
        "https://i.imgur.com/9Xd0s3Y.png",
        "https://i.imgur.com/enz5kfa.png",
        "https://i.imgur.com/1vtsFtF.png",
        "https://i.imgur.com/3beMtf8.png",
        "https://i.imgur.com/0qsNN2f.png",
        "https://i.imgur.com/orzAm6z.png",
        "https://i.imgur.com/2Cj2trS.png",
        "https://i.imgur.com/Rf0c8si.png",
        "https://i.imgur.com/FEwzNfT.png",
    ],
    "purple": [
        "https://i.imgur.com/ACKlpwU.png",
        "https://i.imgur.com/P3mgFlp.png",
        "https://i.imgur.com/SpUB1fM.png",
        "https://i.imgur.com/3aBJXJN.png",
        "https://i.imgur.com/RrGSuFk.png",
        "https://i.imgur.com/eZdhcu0.png",
        "https://i.imgur.com/GPMXYBc.png",
    ],
}

STYLE_4 = [
    "https://i.imgur.com/wy83j2k.png",
    "https://i.imgur.com/7ZxrVfh.png",
    "https://i.imgur.com/7hfEObn.png",
    "https://i.imgur.com/GSCbvIM.png",
    "https://i.imgur.com/hFU8N24.png",
    "https://i.imgur.com/T03rsMr.png",
    "https://i.imgur.com/hdT0dzJ.png",
    "https://i.imgur.com/wEwasHO.png",
    "https://i.imgur.com/5IJf1gB.png",
    "https://i.imgur.com/o6anTbt.png",
]

class EmbedSpec:
    def __init__(self, color: int, title_pool: list[str], desc_pool: list[str], fields_pool: list[dict],
                 thumbnail_policy: dict):
        self.color = color
        self.title_pool = title_pool
        self.desc_pool = desc_pool
        self.fields_pool = fields_pool
        self.thumbnail_policy = thumbnail_policy

class Embedder:
    def __init__(self, cfg, db):
        self.cfg = cfg
        self.db = db

    async def build_embed(self, gid: int, context: str, spec: EmbedSpec, fmt: dict, is_dm: bool) -> discord.Embed:
        title = random.choice(spec.title_pool) if spec.title_pool else ""
        desc = random.choice(spec.desc_pool) if spec.desc_pool else ""
        if fmt:
            title = title.format(**fmt)
            desc = desc.format(**fmt)

        e = discord.Embed(title=title, description=desc, color=spec.color)

        for f in spec.fields_pool or []:
            name = f["name"]
            val = random.choice(f["values"]) if isinstance(f["values"], list) else str(f["values"])
            if fmt:
                name = name.format(**fmt)
                val = val.format(**fmt)
            e.add_field(name=name, value=val, inline=bool(f.get("inline", False)))

        # thumbnail selection
        pol = spec.thumbnail_policy or {"kind": "style_1", "emotions": ["neutral"]}
        kind = pol.get("kind", "style_1")

        if kind == "style_4":
            e.set_thumbnail(url=random.choice(STYLE_4))
            return e

        if kind == "style_2" and is_dm:
            themes = pol.get("themes", ["blue"])
            theme = random.choice(themes)
            urls = STYLE_2.get(theme, STYLE_2["blue"])
            e.set_thumbnail(url=random.choice(urls))
            return e

        # default public: style_1
        emos = pol.get("emotions", ["neutral"])
        emo = random.choice(emos)
        urls = STYLE_1.get(emo, STYLE_1["neutral"])
        e.set_thumbnail(url=random.choice(urls))
        return e

# Backward compatibility function
def isla_embed(title: str, desc: str, color: int = 0x673AB7) -> discord.Embed:
    """Simple embed helper for backward compatibility."""
    e = discord.Embed(title=title, description=desc, color=color)
    return e
