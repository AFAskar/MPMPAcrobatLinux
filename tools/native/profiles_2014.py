"""Shared 2014 MPMB comprehensive class/multiclass profiles and assertions.

Covers all 13 core 2014 classes (Barbarian, Bard, Cleric, Druid, Fighter, Monk,
Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard, Artificer) plus Multiclassing,
2014 races/subraces, backgrounds, feats, weapons, spell sheets, Wild Shape,
Companion pages, resource spending, selective short/long rests, cold reopen,
and mixed-engine follow-up edits.
"""
import json

CONSOLE_SENTINEL = "MPMB 2014 comprehensive class workflow console sentinel"


def _stats(str_, dex, con, int_, wis, cha):
    return [
        ("edit", "Str", str(str_)),
        ("edit", "Dex", str(dex)),
        ("edit", "Con", str(con)),
        ("edit", "Int", str(int_)),
        ("edit", "Wis", str(wis)),
        ("edit", "Cha", str(cha)),
    ]


def spend_resource_js(prefix, amount):
    return (
        "(function(){"
        "for(var i=0;i<numFields;i++){"
        "var n=getNthFieldName(i),m=/^Limited Feature (\\d+)$/.exec(n);"
        "if(m&&getField(n).valueAsString.indexOf("
        + json.dumps(prefix)
        + ")===0){getField('Limited Feature Used '+m[1]).value="
        + json.dumps(str(amount))
        + ";return m[1];}}"
        "throw Error('Missing resource: '+"
        + json.dumps(prefix)
        + ");})()"
    )


PROFILES = {
    "barbarian": {
        "batch": "A",
        "description": "2014 Berserker Barbarian + Half-Orc + Outlander + Rage scaling + Greataxe + L1/3/5/10",
        "phases": [
            (
                "barbarian-l3-berserker",
                _stats(18, 14, 16, 8, 12, 10)
                + [
                    ("edit", "Race", "Half-Orc"),
                    ("edit", "Background", "Outlander"),
                    ("cmd", "ApplyClasses('Barbarian (Berserker) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Greataxe"),
                ],
            ),
            (
                "barbarian-l5-spend-rest",
                [
                    ("cmd", "ApplyClasses('Barbarian (Berserker) 5', false)"),
                    ("eval", spend_resource_js("Rage", 2)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "barbarian-l5-long-rest",
                [
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "barbarian-l10-mixed",
            [
                ("cmd", "ApplyClasses('Barbarian (Berserker) 10', false)"),
            ],
        ),
    },
    "bard": {
        "batch": "A",
        "description": "2014 College of Lore Bard + Half-Elf + Entertainer + Inspiration / Font SR + Spell Sheet",
        "phases": [
            (
                "bard-l3-lore",
                _stats(10, 14, 14, 12, 10, 18)
                + [
                    ("edit", "Race", "Half-Elf"),
                    ("edit", "Background", "Entertainer"),
                    ("cmd", "ApplyClasses('Bard (College of Lore) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Rapier"),
                ],
            ),
            (
                "bard-l6-font-spells",
                [
                    ("cmd", "ApplyClasses('Bard (College of Lore) 6', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "bard-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Bardic Inspiration", 3)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "bard-l10-mixed",
            [
                ("cmd", "ApplyClasses('Bard (College of Lore) 10', false)"),
            ],
        ),
    },
    "cleric": {
        "batch": "A",
        "description": "2014 Life Domain Cleric + Hill Dwarf + Acolyte + Heavy Armor + Channel Divinity SR + Spell Sheet",
        "phases": [
            (
                "cleric-l1-life",
                _stats(14, 10, 14, 10, 16, 12)
                + [
                    ("edit", "Race", "Hill Dwarf"),
                    ("edit", "Background", "Acolyte"),
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 1', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Mace"),
                ],
            ),
            (
                "cleric-l6-cd-spells",
                [
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 6', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "cleric-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Channel Divinity", 2)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "cleric-l14-progress",
                [
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 14', false)"),
                ],
            ),
            (
                "cleric-l5-down",
                [
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 5', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "cleric-l9-mixed",
            [
                ("cmd", "ApplyClasses('Cleric (Life Domain) 9', false)"),
            ],
        ),
    },
    "druid": {
        "batch": "A",
        "description": "2014 Circle of the Moon Druid + Wood Elf + Hermit + Wild Shape (Wolf) + Spell Sheet",
        "phases": [
            (
                "druid-l3-moon",
                _stats(10, 14, 14, 12, 16, 10)
                + [
                    ("edit", "Race", "Wood Elf"),
                    ("edit", "Background", "Hermit"),
                    ("cmd", "ApplyClasses('Druid (Circle of the Moon) 3', false)"),
                ],
            ),
            (
                "druid-l6-wildshape-spells",
                [
                    ("cmd", "ApplyClasses('Druid (Circle of the Moon) 6', false)"),
                    ("cmd", "DoTemplate('WSfront', 'Add', null, true)"),
                    ("edit", "P6.WSfront.Wildshape.Race.1", "wolf"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "druid-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Wild Shape", 2)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "druid-l10-mixed",
            [
                ("cmd", "ApplyClasses('Druid (Circle of the Moon) 10', false)"),
            ],
        ),
    },
    "fighter": {
        "batch": "A",
        "description": "2014 Battle Master Fighter + Human + Soldier + Second Wind / Action Surge / Superiority Dice SR",
        "phases": [
            (
                "fighter-l3-battlemaster",
                _stats(18, 12, 16, 10, 12, 10)
                + [
                    ("edit", "Race", "Human"),
                    ("edit", "Background", "Soldier"),
                    ("cmd", "ApplyClasses('Fighter (Battle Master) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Longsword"),
                ],
            ),
            (
                "fighter-l7-spend-rest",
                [
                    ("cmd", "ApplyClasses('Fighter (Battle Master) 7', false)"),
                    ("eval", spend_resource_js("Action Surge", 1)),
                    ("eval", spend_resource_js("Combat Superiority", 3)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "fighter-l11-progress",
                [
                    ("cmd", "ApplyClasses('Fighter (Battle Master) 11', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "fighter-l5-mixed",
            [
                ("cmd", "ApplyClasses('Fighter (Battle Master) 5', false)"),
            ],
        ),
    },
    "monk": {
        "batch": "B",
        "description": "2014 Way of Shadow Monk + Wood Elf + Urchin + Unarmored Defense + Ki SR + Diamond Soul L14",
        "phases": [
            (
                "monk-l3-shadow",
                _stats(10, 18, 14, 10, 16, 10)
                + [
                    ("edit", "Race", "Wood Elf"),
                    ("edit", "Background", "Urchin"),
                    ("cmd", "ApplyClasses('Monk (Way of Shadow) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Shortsword"),
                ],
            ),
            (
                "monk-l6-spend-rest",
                [
                    ("cmd", "ApplyClasses('Monk (Way of Shadow) 6', false)"),
                    ("eval", spend_resource_js("Ki Points", 4)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "monk-l14-diamond-soul",
                [
                    ("cmd", "ApplyClasses('Monk (Way of Shadow) 14', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "monk-l8-mixed",
            [
                ("cmd", "ApplyClasses('Monk (Way of Shadow) 8', false)"),
            ],
        ),
    },
    "paladin": {
        "batch": "B",
        "description": "2014 Oath of Devotion Paladin + Dragonborn + Noble + Lay on Hands LR / Channel Divinity SR + Aura + Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "paladin-l2-setup",
                _stats(16, 10, 14, 10, 12, 16)
                + [
                    ("edit", "Race", "Dragonborn"),
                    ("edit", "Background", "Noble"),
                    ("cmd", "ApplyClasses('Paladin 2', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Longsword"),
                    ("edit", "Attack.2.Weapon Selection", "Javelin"),
                ],
            ),
            (
                "paladin-l6-devotion-aura-spells",
                [
                    ("cmd", "ApplyClasses('Paladin (Oath of Devotion) 6', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "paladin-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Lay on Hands", 15)),
                    ("eval", spend_resource_js("Channel Divinity", 1)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "paladin-l11-mixed",
            [
                ("cmd", "ApplyClasses('Paladin (Oath of Devotion) 11', false)"),
                ("cmd", "resetLimFeaUsed('long rest')"),
            ],
        ),
    },
    "ranger": {
        "batch": "B",
        "description": "2014 Hunter Ranger + High Elf + Outlander + Longbow + Companion Page (Timber Wolf) + Spell Sheet",
        "phases": [
            (
                "ranger-l3-hunter",
                _stats(12, 16, 14, 10, 16, 10)
                + [
                    ("edit", "Race", "High Elf"),
                    ("edit", "Background", "Outlander"),
                    ("cmd", "ApplyClasses('Ranger (Hunter) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Longbow"),
                ],
            ),
            (
                "ranger-l5-companion-spells",
                [
                    ("cmd", "ApplyClasses('Ranger (Hunter) 5', false)"),
                    ("cmd", "DoTemplate('AScomp', 'Add', null, true)"),
                    ("edit", "P5.AScomp.Comp.Race", "Wolf"),
                    ("edit", "P5.AScomp.Comp.Desc.Name", "Timber"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
        ],
        "mixed_followup": (
            "ranger-l9-mixed",
            [
                ("cmd", "ApplyClasses('Ranger (Hunter) 9', false)"),
            ],
        ),
    },
    "rogue": {
        "batch": "B",
        "description": "2014 Thief Rogue + Lightfoot Halfling + Criminal + Sneak Attack L1/5/11/20 + Reliable Talent",
        "phases": [
            (
                "rogue-l1-criminal",
                _stats(10, 16, 14, 12, 12, 14)
                + [
                    ("edit", "Race", "Lightfoot Halfling"),
                    ("edit", "Background", "Criminal"),
                    ("cmd", "ApplyClasses('Rogue 1', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Dagger"),
                    ("edit", "Attack.2.Weapon Selection", "Shortbow"),
                ],
            ),
            (
                "rogue-l5-thief",
                [
                    ("cmd", "ApplyClasses('Rogue (Thief) 5', false)"),
                ],
            ),
            (
                "rogue-l11-reliable",
                [
                    ("cmd", "ApplyClasses('Rogue (Thief) 11', false)"),
                ],
            ),
            (
                "rogue-l20-capstone",
                [
                    ("cmd", "ApplyClasses('Rogue (Thief) 20', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "rogue-l7-mixed",
            [
                ("cmd", "ApplyClasses('Rogue (Thief) 7', false)"),
            ],
        ),
    },
    "sorcerer": {
        "batch": "C",
        "description": "2014 Draconic Bloodline Sorcerer + Tiefling + Metamagic + Draconic Resilience AC + Sorcery Points + Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "sorcerer-l3-draconic",
                _stats(8, 14, 14, 10, 12, 18)
                + [
                    ("edit", "Race", "Tiefling"),
                    ("cmd", "ApplyClasses('Sorcerer (Draconic Bloodline) 3', false)"),
                    ("cmd", "ClassFeatureOptions(['sorcerer', 'metamagic', 'quickened spell', true, 'add'])"),
                    ("cmd", "ClassFeatureOptions(['sorcerer', 'metamagic', 'subtle spell', true, 'add'])"),
                ],
            ),
            (
                "sorcerer-l6-spells",
                [
                    ("cmd", "ApplyClasses('Sorcerer (Draconic Bloodline) 6', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "sorcerer-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Sorcery Points", 4)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "sorcerer-l10-mixed",
            [
                ("cmd", "ApplyClasses('Sorcerer (Draconic Bloodline) 10', false)"),
            ],
        ),
    },
    "warlock": {
        "batch": "C",
        "description": "2014 The Fiend Warlock + Tiefling + Invocations + Pact Magic L3/11/17 + Mystic Arcanum + Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "warlock-l3-fiend",
                _stats(10, 14, 14, 12, 10, 18)
                + [
                    ("edit", "Race", "Tiefling"),
                    ("cmd", "ApplyClasses('Warlock (The Fiend) 3', false)"),
                    ("cmd", "ClassFeatureOptions(['warlock', 'eldritch invocations', \"devil's sight\", true, 'add'])"),
                    ("cmd", "ClassFeatureOptions(['warlock', 'eldritch invocations', 'agonizing blast', true, 'add'])"),
                ],
            ),
            (
                "warlock-l11-pact-spells",
                [
                    ("cmd", "ApplyClasses('Warlock (The Fiend) 11', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "warlock-l17-arcanum",
                [
                    ("cmd", "ApplyClasses('Warlock (The Fiend) 17', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "warlock-l5-mixed",
            [
                ("cmd", "ApplyClasses('Warlock (The Fiend) 5', false)"),
            ],
        ),
    },
    "wizard": {
        "batch": "C",
        "description": "2014 School of Evocation Wizard + High Elf + Sage + Arcane Recovery LR + Spell Sheet",
        "phases": [
            (
                "wizard-l3-evocation",
                _stats(8, 14, 14, 18, 12, 10)
                + [
                    ("edit", "Race", "High Elf"),
                    ("edit", "Background", "Sage"),
                    ("cmd", "ApplyClasses('Wizard (Evocation) 3', false)"),
                ],
            ),
            (
                "wizard-l10-spells",
                [
                    ("cmd", "ApplyClasses('Wizard (Evocation) 10', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "wizard-l10-spend-rest",
                [
                    ("eval", spend_resource_js("Arcane Recovery", 1)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "wizard-l6-mixed",
            [
                ("cmd", "ApplyClasses('Wizard (Evocation) 6', false)"),
            ],
        ),
    },
    "artificer": {
        "batch": "C",
        "description": "2014 Battle Smith Artificer + Rock Gnome + Guild Artisan + Infuse Item + Flash of Genius + Spell Sheet",
        "phases": [
            (
                "artificer-l3-battlesmith",
                _stats(10, 14, 14, 18, 12, 10)
                + [
                    ("edit", "Race", "Rock Gnome"),
                    ("edit", "Background", "Guild Artisan"),
                    ("cmd", "ApplyClasses('Artificer (Battle Smith) 3', false)"),
                ],
            ),
            (
                "artificer-l7-flash-spells",
                [
                    ("cmd", "ApplyClasses('Artificer (Battle Smith) 7', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "artificer-l7-spend-rest",
                [
                    ("eval", spend_resource_js("Flash of Genius", 2)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "artificer-l11-mixed",
            [
                ("cmd", "ApplyClasses('Artificer (Battle Smith) 11', false)"),
            ],
        ),
    },
    "multiclass": {
        "batch": "C",
        "description": "2014 Multiclass: Paladin 6 / Warlock 3 -> Fighter 3 / Wizard 5 -> Fighter 5 / Wizard 5",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "mc-pal6-war3",
                _stats(16, 10, 14, 10, 12, 18)
                + [
                    ("edit", "Race", "Human"),
                    ("cmd", "ApplyClasses('Paladin (Oath of Devotion) 6, Warlock (The Fiend) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Longsword"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "mc-pal6-war3-rests",
                [
                    ("eval", spend_resource_js("Lay on Hands", 10)),
                    ("eval", spend_resource_js("Channel Divinity", 1)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "mc-ftr3-wiz5",
                [
                    ("cmd", "ApplyClasses('Fighter (Champion) 3, Wizard (Evocation) 5', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
        ],
        "mixed_followup": (
            "mc-ftr5-wiz5-mixed",
            [
                ("cmd", "ApplyClasses('Fighter (Champion) 5, Wizard (Evocation) 5', false)"),
            ],
        ),
    },
}


def find_row(state, prefix):
    matches = [r for r in state["rows"] if r["name"].startswith(prefix)]
    assert len(matches) == 1, (prefix, state["rows"])
    return matches[0]


def validate_profile_state(profile_name, phase_label, state):
    assert not state["errors"], (profile_name, phase_label, state["errors"])
    assert not state["unavailable"], (profile_name, phase_label, state["unavailable"])
    f = state["fields"]

    if profile_name == "barbarian":
        if phase_label == "barbarian-l3-berserker":
            assert f["Character Level"] == "3" and f["Proficiency Bonus"] == "2"
            assert state["identity"]["barbarian"]["subclass"] == "barbarian-berserker"
            assert find_row(state, "Rage")["max"] == "3"
        elif phase_label == "barbarian-l5-spend-rest":
            assert f["Character Level"] == "5" and f["Proficiency Bonus"] == "3"
            assert find_row(state, "Rage")["used"] == "2", "Short rest must preserve spent 2014 Rage"
        elif phase_label in ("barbarian-l5-long-rest", "barbarian-l5-long-rest-cold"):
            assert find_row(state, "Rage")["used"] == "", "Long rest must clear 2014 Rage"
        elif phase_label == "barbarian-l10-mixed":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"
            assert find_row(state, "Rage")["max"] == "4"

    elif profile_name == "bard":
        if phase_label == "bard-l3-lore":
            assert f["Character Level"] == "3" and state["identity"]["bard"]["subclass"] == "bard-college of lore"
            assert find_row(state, "Bardic Inspiration")["max"] == "4"
        elif phase_label == "bard-l6-font-spells":
            assert f["Character Level"] == "6" and "bard" in state["spells"]
            assert state["pages"] > 7 and (
                state["templates"]["SSfront"].count(",") >= 1 or state["templates"]["SSmore"].count(",") >= 1
            )
        elif phase_label in ("bard-l6-spend-rest", "bard-l6-spend-rest-cold"):
            assert find_row(state, "Bardic Inspiration")["used"] == "", "Font of Inspiration short rest must clear Inspiration"
        elif phase_label == "bard-l10-mixed":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"

    elif profile_name == "cleric":
        if phase_label == "cleric-l1-life":
            assert f["Character Level"] == "1" and state["identity"]["cleric"]["subclass"] == "cleric-life domain"
        elif phase_label == "cleric-l6-cd-spells":
            assert f["Character Level"] == "6" and "cleric" in state["spells"]
            assert find_row(state, "Channel Divinity")["max"] == "2"
        elif phase_label == "cleric-l6-spend-rest":
            assert find_row(state, "Channel Divinity")["used"] == "", "2014 Channel Divinity resets on short rest"
        elif phase_label == "cleric-l14-progress":
            assert f["Character Level"] == "14" and f["Proficiency Bonus"] == "5"
        elif phase_label in ("cleric-l5-down", "cleric-l5-down-cold"):
            assert f["Character Level"] == "5" and f["Proficiency Bonus"] == "3"
        elif phase_label == "cleric-l9-mixed":
            assert f["Character Level"] == "9" and f["Proficiency Bonus"] == "4"

    elif profile_name == "druid":
        if phase_label == "druid-l3-moon":
            assert f["Character Level"] == "3" and state["identity"]["druid"]["subclass"] == "druid-circle of the moon"
        elif phase_label == "druid-l6-wildshape-spells":
            assert f["Character Level"] == "6" and "druid" in state["spells"]
            assert state["templates"]["WSfront"].count(",") >= 1
            ws_pre = state["templates"]["WSfront"].split(",")[1]
            assert state["notesAndActions"][ws_pre + "Wildshape.Race.1"] == "wolf"
            assert state["notesAndActions"][ws_pre + "Wildshape.1.Ability.Str.Score"] == "12"
        elif phase_label in ("druid-l6-spend-rest", "druid-l6-spend-rest-cold"):
            assert find_row(state, "Wild Shape")["used"] == "", "2014 Wild Shape resets on short rest"
        elif phase_label == "druid-l10-mixed":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"

    elif profile_name == "fighter":
        if phase_label == "fighter-l3-battlemaster":
            assert f["Character Level"] == "3" and state["identity"]["fighter"]["subclass"] == "fighter-battle master"
            assert find_row(state, "Combat Superiority")["max"] == "4"
        elif phase_label == "fighter-l7-spend-rest":
            assert f["Character Level"] == "7"
            assert find_row(state, "Action Surge")["used"] == ""
            assert find_row(state, "Combat Superiority")["used"] == ""
        elif phase_label in ("fighter-l11-progress", "fighter-l11-progress-cold"):
            assert f["Character Level"] == "11" and f["Proficiency Bonus"] == "4"
        elif phase_label == "fighter-l5-mixed":
            assert f["Character Level"] == "5" and f["Proficiency Bonus"] == "3"

    elif profile_name == "monk":
        if phase_label == "monk-l3-shadow":
            assert f["Character Level"] == "3" and state["identity"]["monk"]["subclass"] == "monk-way of shadow"
            assert find_row(state, "Ki Points")["max"] == "3"
        elif phase_label == "monk-l6-spend-rest":
            assert f["Character Level"] == "6" and find_row(state, "Ki Points")["used"] == ""
        elif phase_label in ("monk-l14-diamond-soul", "monk-l14-diamond-soul-cold"):
            assert f["Character Level"] == "14" and f["Proficiency Bonus"] == "5"
            assert int(f["Cha ST Mod"]) == 5, ("Diamond Soul grants +5 Cha ST", f["Cha ST Mod"])
        elif phase_label == "monk-l8-mixed":
            assert f["Character Level"] == "8" and f["Proficiency Bonus"] == "3"

    elif profile_name == "paladin":
        if phase_label == "paladin-l2-setup":
            assert f["Character Level"] == "2" and find_row(state, "Lay on Hands")["max"] == "10"
        elif phase_label == "paladin-l6-devotion-aura-spells":
            assert f["Character Level"] == "6" and "paladin" in state["spells"]
            assert int(f["Dex ST Mod"]) >= 3, ("Aura of Protection Cha +3", f["Dex ST Mod"])
        elif phase_label in ("paladin-l6-spend-rest", "paladin-l6-spend-rest-cold"):
            assert find_row(state, "Lay on Hands")["used"] == "15", "Short rest must preserve Lay on Hands"
            assert find_row(state, "Channel Divinity")["used"] == "", "2014 Channel Divinity clears on short rest"
        elif phase_label == "paladin-l11-mixed":
            assert f["Character Level"] == "11" and find_row(state, "Lay on Hands")["used"] == ""

    elif profile_name == "ranger":
        if phase_label == "ranger-l3-hunter":
            assert f["Character Level"] == "3" and state["identity"]["ranger"]["subclass"] == "ranger-hunter"
        elif phase_label in ("ranger-l5-companion-spells", "ranger-l5-companion-spells-cold"):
            assert f["Character Level"] == "5" and "ranger" in state["spells"]
            comp_pre = state["templates"]["AScomp"].split(",")[-1]
            assert state["notesAndActions"][comp_pre + "Comp.Desc.Name"] == "Timber"
            assert state["notesAndActions"][comp_pre + "Comp.Race"].lower() == "wolf"
        elif phase_label == "ranger-l9-mixed":
            assert f["Character Level"] == "9" and f["Proficiency Bonus"] == "4"

    elif profile_name == "rogue":
        if phase_label == "rogue-l1-criminal":
            assert f["Character Level"] == "1" and "1d6" in state["notesAndActions"]["Class Features"]
        elif phase_label == "rogue-l5-thief":
            assert f["Character Level"] == "5" and state["identity"]["rogue"]["subclass"] == "rogue-thief"
            assert "3d6" in state["notesAndActions"]["Class Features"]
        elif phase_label == "rogue-l11-reliable":
            assert f["Character Level"] == "11" and "6d6" in state["notesAndActions"]["Class Features"]
        elif phase_label in ("rogue-l20-capstone", "rogue-l20-capstone-cold"):
            assert f["Character Level"] == "20" and "10d6" in state["notesAndActions"]["Class Features"]
        elif phase_label == "rogue-l7-mixed":
            assert f["Character Level"] == "7" and "4d6" in state["notesAndActions"]["Class Features"]

    elif profile_name == "sorcerer":
        if phase_label == "sorcerer-l3-draconic":
            assert f["Character Level"] == "3" and state["identity"]["sorcerer"]["subclass"] == "sorcerer-draconic bloodline"
            assert int(f["AC"]) == 15, ("Draconic Resilience 13 + Dex 2 = 15", f["AC"])
            assert find_row(state, "Sorcery Points")["max"] == "3"
        elif phase_label == "sorcerer-l6-spells":
            assert f["Character Level"] == "6" and "sorcerer" in state["spells"]
        elif phase_label in ("sorcerer-l6-spend-rest", "sorcerer-l6-spend-rest-cold"):
            assert find_row(state, "Sorcery Points")["used"] == ""
        elif phase_label == "sorcerer-l10-mixed":
            assert f["Character Level"] == "10" and find_row(state, "Sorcery Points")["max"] == "10"

    elif profile_name == "warlock":
        if phase_label == "warlock-l3-fiend":
            assert f["Character Level"] == "3" and state["identity"]["warlock"]["subclass"] == "warlock-the fiend"
        elif phase_label == "warlock-l11-pact-spells":
            assert f["Character Level"] == "11" and "warlock" in state["spells"]
        elif phase_label in ("warlock-l17-arcanum", "warlock-l17-arcanum-cold"):
            assert f["Character Level"] == "17" and f["Proficiency Bonus"] == "6"
        elif phase_label == "warlock-l5-mixed":
            assert f["Character Level"] == "5" and f["Proficiency Bonus"] == "3"

    elif profile_name == "wizard":
        if phase_label == "wizard-l3-evocation":
            assert f["Character Level"] == "3" and state["identity"]["wizard"]["subclass"] == "wizard-evocation"
        elif phase_label == "wizard-l10-spells":
            assert f["Character Level"] == "10" and "wizard" in state["spells"]
        elif phase_label in ("wizard-l10-spend-rest", "wizard-l10-spend-rest-cold"):
            assert find_row(state, "Arcane Recovery")["used"] == ""
        elif phase_label == "wizard-l6-mixed":
            assert f["Character Level"] == "6" and f["Proficiency Bonus"] == "3"

    elif profile_name == "artificer":
        if phase_label == "artificer-l3-battlesmith":
            assert f["Character Level"] == "3" and state["identity"]["artificer"]["subclass"] == "artificer-battle smith"
        elif phase_label == "artificer-l7-flash-spells":
            assert f["Character Level"] == "7" and "artificer" in state["spells"]
            assert find_row(state, "Flash of Genius")["max"] == "4"
        elif phase_label in ("artificer-l7-spend-rest", "artificer-l7-spend-rest-cold"):
            assert find_row(state, "Flash of Genius")["used"] == ""
        elif phase_label == "artificer-l11-mixed":
            assert f["Character Level"] == "11" and f["Proficiency Bonus"] == "4"

    elif profile_name == "multiclass":
        if phase_label == "mc-pal6-war3":
            assert f["Character Level"] == "9" and "paladin" in state["identity"] and "warlock" in state["identity"]
            assert int(f["Dex ST Mod"]) >= 4, ("Aura of Protection +4 Cha", f["Dex ST Mod"])
        elif phase_label == "mc-pal6-war3-rests":
            assert find_row(state, "Lay on Hands")["used"] == "10"
            assert find_row(state, "Channel Divinity")["used"] == ""
        elif phase_label in ("mc-ftr3-wiz5", "mc-ftr3-wiz5-cold"):
            assert f["Character Level"] == "8" and "fighter" in state["identity"] and "wizard" in state["identity"]
            assert f["HD1 Level"] == "3" and f["HD2 Level"] == "5"
        elif phase_label == "mc-ftr5-wiz5-mixed":
            assert f["Character Level"] == "10" and f["HD1 Level"] == "5" and f["HD2 Level"] == "5"
