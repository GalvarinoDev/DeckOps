/*
    DeckOps In-Game Create-a-Class Editor v1.0 (IW5 / MW3)
    Server-side GSC script for Plutonium IW5 dedicated servers.
    Drop into: storage/iw5/scripts/deckops_cac.gsc

    Ported from IW4x MW2 CAC v2.0 (menu input and hints from v2.1), adapted for the MW3 class system:
        - IW5 weapon codenames (iw5_ prefix)
        - Weapon Proficiencies (per weapon class)
        - Dual attachment support (2nd slot requires Attachments proficiency)
        - MW3 perks, equipment, tacticals, deathstreaks
        - Offline: no unlock gating, everything is available
        - Edits go into the "gamemode" loadout (player data writes drop the client on IW5 LAN)
        - Per-weapon attachment restrictions (isValidCombination)

    Controls:
        - Open: CHOOSE CLASS in the in-game menu (hub: Class Editor, Choose Classes, Map / Mode, Bot Warfare)
        - A real game menu (mouse, keyboard, controller): our plutonium_patch_mp.ff replaces the stock
          muteplayer menu with it (client and server storage/iw5/zone, built by build_mw3_menu.py)

    Credits:
        - Divity (k) - Original in-game CAC concept and setPlayerData backend
        - EternalHabit/Antiga - Mapvote HUD pattern reference
        - DeckOps Community
*/

#include common_scripts\utility;
#include maps\mp\_utility;
#include maps\mp\gametypes\_hud_util;

init()
{
    dcacCatalog();
    buildStreakData();
    buildNameLookup();
    // Weapon pictures are drawn by the menu from a dvar, so they need no precache (precaching more than
    // about 14 materials overflowed G_FindConfigstringIndex and stopped the server, PC 2026-10-10)

    level thread onPlayerConnect();
    level thread applyMatchOptions();
}

onPlayerConnect()
{
    for (;;)
    {
        level waittill("connected", player);
        if (!isDefined(player.pers["isBot"]) || player.pers["isBot"] == false)
        {
            player initCac();
            player thread watchForMenuOpen();
            player thread watchDeath();
            player thread watchSpawnLoadout();
        }
    }
}

// --- DEATH WATCHER (close the menu if the player dies with it open)

watchDeath()
{
    self endon("disconnect");
    for (;;)
    {
        self waittill("death");
        self cacCleanup();
    }
}

// Every menu function ends on death, so the menu, freeze and open flag are released here too
cacCleanup()
{
    // only a menu that was open counts toward resuming the bots
    if (isDefined(self.cac_ui))
    {
        self botsResume();
        self closepopupmenu();
    }
    self.cac_ui = undefined;
    self freezeControlsWrapper(false);
    self setClientDvar("actionSlotsHide", "0");
    self.cac_open = false;
}

// Test builds: +set dcac_debug 1 logs the menu flow to games_mp.log
dlog(msg)
{
    if (getDvarInt("dcac_debug"))
        logPrint("DCAC;" + self.name + ";" + msg + "\n");
}

// --- CLASS STORAGE AND ITEM LIST HELPERS

// Five classes in self.dcac[0..4]. Every edit goes to self.dcac[self.dcac_cur]. The class in use is copied into
// self.pers["gamemodeLoadout"], which _class.gsc gives for class "gamemode" without unlock checks. Server dvars
// per guid keep them across map changes: dcac_<guid>_<n> (one class each, a dvar holds 1024 characters at most)
// and dcac_use_<guid> (the class in use, "-" for none). Plutonium IW5 has no GSC file I/O (no fs_*, openfile
// returns undefined, PC 2026-10-10), so every save is also a games_mp.log line (DCAC;class / DCAC;use) that
// lan_server.sh replays as +set on the next server start.
cacKeys()
{
    k = [];
    k[0] = "loadoutPrimary";              k[1] = "loadoutPrimaryAttachment";    k[2] = "loadoutPrimaryAttachment2";
    k[3] = "loadoutPrimaryBuff";          k[4] = "loadoutSecondary";            k[5] = "loadoutSecondaryAttachment";
    k[6] = "loadoutSecondaryAttachment2"; k[7] = "loadoutSecondaryBuff";        k[8] = "loadoutEquipment";
    k[9] = "loadoutOffhand";              k[10] = "loadoutPerk1";               k[11] = "loadoutPerk2";
    k[12] = "loadoutPerk3";               k[13] = "loadoutDeathstreak";
    k[14] = "loadoutStreakType";          k[15] = "loadoutKillstreak1";         k[16] = "loadoutKillstreak2";
    k[17] = "loadoutKillstreak3";
    return k;
}

cacDefault()
{
    l = [];
    l["loadoutPrimary"] = "iw5_m4";           l["loadoutPrimaryAttachment"] = "none";   l["loadoutPrimaryAttachment2"] = "none";
    l["loadoutPrimaryBuff"] = "specialty_null"; l["loadoutPrimaryCamo"] = "none";       l["loadoutPrimaryReticle"] = "none";
    l["loadoutSecondary"] = "iw5_usp45";      l["loadoutSecondaryAttachment"] = "none"; l["loadoutSecondaryAttachment2"] = "none";
    l["loadoutSecondaryBuff"] = "specialty_null"; l["loadoutSecondaryCamo"] = "none";   l["loadoutSecondaryReticle"] = "none";
    l["loadoutEquipment"] = "frag_grenade_mp"; l["loadoutOffhand"] = "flash_grenade_mp";
    l["loadoutPerk1"] = "specialty_longersprint"; l["loadoutPerk2"] = "specialty_quickdraw"; l["loadoutPerk3"] = "specialty_bulletaccuracy";
    l["loadoutDeathstreak"] = "specialty_null"; l["loadoutJuggernaut"] = false;
    l["loadoutStreakType"] = "streaktype_assault";
    l["loadoutKillstreak1"] = "uav"; l["loadoutKillstreak2"] = "predator_missile"; l["loadoutKillstreak3"] = "helicopter";
    return l;
}

initCac()
{
    keys = cacKeys();
    self.dcac = [];
    for (n = 0; n < 5; n++)
    {
        l = cacDefault();
        vals = strTok(getDvar("dcac_" + self.guid + "_" + n), ",");
        if (vals.size == keys.size)
            for (i = 0; i < keys.size; i++)
                l[keys[i]] = vals[i];
        self.dcac[n] = l;
    }
    self.dcac_cur = 0;
    self.dcac_use = undefined;
    use = getDvar("dcac_use_" + self.guid);
    if (use != "" && use != "-")
        self.dcac_use = int(use);
}

cacSet(key, value)
{
    self.dcac[self.dcac_cur][key] = value;
    keys = cacKeys();
    str = "";
    for (i = 0; i < keys.size; i++)
    {
        if (i > 0) str += ",";
        str += self.dcac[self.dcac_cur][keys[i]];
    }
    setDvar("dcac_" + self.guid + "_" + self.dcac_cur, str);
    // Read back by lan_server.sh: the last DCAC;class line per guid and class
    logPrint("DCAC;class;" + self.guid + ";" + self.dcac_cur + ";" + str + "\n");
}

// The class in use (undefined: MW3's own class)
cacSetUse(n)
{
    self.dcac_use = n;
    use = "-";
    if (isDefined(n)) use = "" + n;
    setDvar("dcac_use_" + self.guid, use);
    logPrint("DCAC;use;" + self.guid + ";" + use + "\n");
}

cacGet(key)
{
    return self.dcac[self.dcac_cur][key];
}

wKey(slot, field)
{
    base = "loadoutPrimary";
    if (slot == 1) base = "loadoutSecondary";
    if (field == "attachment0") return base + "Attachment";
    if (field == "attachment1") return base + "Attachment2";
    if (field == "buff") return base + "Buff";
    return base;
}

perkKey(slot)
{
    if (slot == 0) return "loadoutEquipment";
    if (slot == 6) return "loadoutOffhand";
    return "loadoutPerk" + slot;
}

getUnlockedItems(listKey, nameKey)
{
    items = [];
    items["keys"] = [];
    items["names"] = [];
    count = 0;

    for (i = 0; i < level.cac[listKey].size; i++)
    {
        {
            items["keys"][count] = level.cac[listKey][i];
            items["names"][count] = level.cac[nameKey][i];
            count++;
        }
    }

    return items;
}

// Second attachment: not the same one, and not a second sight or underbarrel
// (buildWeaponName in _class.gsc only maps one rail optic)
attachGroup(a)
{
    if (a == "acog" || a == "eotech" || a == "hybrid" || a == "reflex" || a == "thermal" || a == "vzscope")
        return "sight";
    if (a == "gl" || a == "shotgun" || a == "grip")
        return "under";
    return a;
}

dropClashingAttachments(list, first)
{
    out = [];
    out["keys"] = [];
    out["names"] = [];
    for (i = 0; i < list["keys"].size; i++)
    {
        a = list["keys"][i];
        if (a != "none" && (a == first || attachGroup(a) == attachGroup(first)))
            continue;
        out["keys"][out["keys"].size] = a;
        out["names"][out["names"].size] = list["names"][i];
    }
    return out;
}

getUnlockedProficiencies(weapon, profListKey, profNameKey)
{
    items = [];
    items["keys"] = [];
    items["names"] = [];
    count = 0;

    for (i = 0; i < level.cac[profListKey].size; i++)
    {
        prof = level.cac[profListKey][i];
        {
            items["keys"][count] = prof;
            items["names"][count] = level.cac[profNameKey][i];
            count++;
        }
    }

    return items;
}

// --- MENU OPEN/CLOSE WATCHER

watchForMenuOpen()
{
    self endon("disconnect");

    self.cac_open = false;
    self thread watchChooseClass();

    for (;;)
    {
        self waittill("cac_toggle");

        if (self.sessionstate != "playing")
            continue;

        if (!self.cac_open)
        {
            self.cac_open = true;
            self thread openHubMenu();
        }
    }
}

// CHOOSE CLASS in the in-game menu sends ("class", "changeclass_marines"/"changeclass_opfor").
// The stock script opens the class list for it. Close that and open the editor instead.
watchChooseClass()
{
    self endon("disconnect");
    for (;;)
    {
        self waittill("menuresponse", menu, response);
        self dlog("menuresponse " + menu + " " + response);
        if (menu == "class" && isSubStr(response, "changeclass"))
            self thread openEditorFromChooseClass();
        // Our zone's Choose Class popup (opened after a team pick) is empty, and a menu can't answer from its onOpen
        // (PC 2026-10-13: left the player spectating), so the stock class pick happens here
        if (isSubStr(menu, "team_marinesopfor") && response != "back")
            self thread joinWithClass0();
    }
}

// MW3's own class pick, as if class0 was clicked in its Choose Class. On that spawn watchSpawnLoadout gives
// the DeckOps class in use and opens our picker
joinWithClass0()
{
    self endon("disconnect");
    wait 0.25;
    if (self.sessionstate == "playing" || self.pers["team"] == "spectator")
        return;
    // closed the way MW3's own scripts close it (closing itself in onOpen left the mouse dead, PC 2026-10-13)
    self closepopupmenu();
    self closeingamemenu();
    self maps\mp\gametypes\_menus::menuClass("class0");
}

openEditorFromChooseClass()
{
    self endon("disconnect");
    wait 0.05;
    self closepopupmenu();
    self closeingamemenu();
    if (!self.cac_open)
        self notify("cac_toggle");
}

// With nothing saved yet, Class 1 starts from the class in use instead of the defaults.
// Reads only: giveLoadout records the base loadout on the player, _class.gsc's getters cover custom classes.
cacSeedFromCurrent()
{
    if (getDvar("dcac_" + self.guid + "_0") != "" || !isDefined(self.loadoutPrimary) || cacModeOwnsLoadout())
        return;

    self.dcac_cur = 0;
    l = self.dcac[0];
    l["loadoutPrimary"] = self.loadoutPrimary;
    l["loadoutSecondary"] = self.loadoutSecondary;
    l["loadoutPrimaryBuff"] = self.loadoutPrimaryBuff;
    l["loadoutSecondaryBuff"] = self.loadoutSecondaryBuff;
    l["loadoutPerk1"] = self.loadoutPerk1;
    l["loadoutPerk2"] = self.loadoutPerk2;
    l["loadoutPerk3"] = self.loadoutPerk3;
    l["loadoutEquipment"] = self.loadoutPerkEquipment;

    if (isSubStr(self.class, "custom") && isDefined(self.class_num))
    {
        n = self.class_num;
        l["loadoutPrimaryAttachment"] = self maps\mp\gametypes\_class::cac_getWeaponAttachment(n, 0);
        l["loadoutPrimaryAttachment2"] = self maps\mp\gametypes\_class::cac_getWeaponAttachmentTwo(n, 0);
        l["loadoutSecondaryAttachment"] = self maps\mp\gametypes\_class::cac_getWeaponAttachment(n, 1);
        l["loadoutSecondaryAttachment2"] = self maps\mp\gametypes\_class::cac_getWeaponAttachmentTwo(n, 1);
        l["loadoutOffhand"] = self maps\mp\gametypes\_class::cac_getOffhand(n);
        l["loadoutDeathstreak"] = self maps\mp\gametypes\_class::cac_getDeathstreak(n);
    }

    if (isDefined(self.streakType) && isDefined(self.killStreaks))
    {
        l["loadoutStreakType"] = "streaktype_" + self.streakType;
        k = 1;
        foreach (ks in self.killStreaks)
        {
            if (k <= 3) l["loadoutKillstreak" + k] = ks;
            k++;
        }
    }

    self.dcac[0] = l;
    // saves the seeded set, so this runs once per session
    self cacSet("loadoutPrimary", l["loadoutPrimary"]);
}

// --- HUB MENU (opened by CHOOSE CLASS)

openHubMenu(index)
{
    self endon("disconnect");
    self endon("death");

    if (isDefined(index)) self.cac_startIndex = index;

    self cacSeedFromCurrent();

    items = [];
    items[0] = "Class Editor";
    items[1] = "Choose Classes";
    items[2] = "Map / Mode";
    items[3] = "Bot Warfare";

    d = [];
    d[0] = "Build and use your five DeckOps classes.";
    d[1] = "Pick which of your five classes to use.";
    d[2] = "Change the mode, the map and the match limits.";
    d[3] = "How many bots, how tough, and how they play.";
    self.cac_descs = d;
    result = self showMenu("MATCH SETTINGS", items, "");
    switch (result)
    {
        case 0:
        case 1:
            if (cacModeOwnsLoadout())
            {
                self iPrintLnBold("^1This mode uses its own loadouts");
                self thread openHubMenu();
            }
            else if (result == 0) self thread openClassList();
            else self thread openChooseClass();
            break;
        case 2: self thread openMatchMenu(); break;
        case 3: self thread openBotMenu(); break;
        default: self cacCleanup(); break;
    }
}

// Hub "Choose Classes": pick one of the five DeckOps classes and use it (as the editor's Use This Class)
openChooseClass()
{
    self endon("disconnect");
    self endon("death");

    if (isDefined(self.dcac_use)) self.cac_startIndex = self.dcac_use;
    result = self showMenu("CHOOSE CLASSES", self classItems(), "");
    if (result == -1) { self thread openHubMenu(1); return; }
    self.dcac_cur = result;
    self thread applyLoadout();
}

// --- MAP / MODE (ends the match and loads the pick through the rotation)

// Time and score limits come from the DSR into scr_<gametype>_*, which the match logic keeps
// reading, so they change live. The DSR resets them on every map, so they are re-applied.
applyMatchOptions()
{
    level endon("game_ended");
    wait 1;
    gt = level.gameType;
    if (getDvar("dcac_base_score_" + gt) == "")
        setDvar("dcac_base_score_" + gt, "" + getDvarInt("scr_" + gt + "_scorelimit"));
    if (getDvar("dcac_opt_timelimit") != "")
        setDvar("scr_" + gt + "_timelimit", getDvar("dcac_opt_timelimit"));
    if (getDvar("dcac_opt_score") != "")
        setDvar("scr_" + gt + "_scorelimit", "" + int(getDvarInt("dcac_base_score_" + gt) * getDvarFloat("dcac_opt_score")));
}

// One setup screen: rows show the pending choice, Start Match applies them together
matchModes()
{
    m = [];
    m["dsr"] = strTok("TDM_default,FFA_default,DOM_default,KC_default,SD_default,HQ_default,DD_default,CTF_default,INF_default", ",");
    m["gt"] = strTok("war,dm,dom,conf,sd,koth,dd,ctf,infect", ",");
    m["name"] = strTok("Team Deathmatch,Free-for-All,Domination,Kill Confirmed,Search and Destroy,Headquarters,Demolition,Capture the Flag,Infected", ",");
    return m;
}

// dcac_maps (set by the offline script) lists the installed maps. DLC maps may be missing.
// DLC names from Bot Warfare's waypoint files, to check against MW3's strings with the Round B catalog.
matchMaps()
{
    keys = strTok("mp_alpha,mp_bootleg,mp_bravo,mp_carbon,mp_dome,mp_exchange,mp_hardhat,mp_interchange,mp_lambeth,mp_mogadishu,mp_paris,mp_plaza2,mp_radar,mp_seatown,mp_underground,mp_village,mp_park,mp_italy,mp_overwatch,mp_morningwood,mp_meteora,mp_cement,mp_qadeem,mp_aground_ss,mp_courtyard_ss,mp_hillside_ss,mp_restrepo_ss,mp_terminal_cls,mp_crosswalk_ss,mp_burn_ss,mp_six_ss,mp_moab,mp_boardwalk,mp_nola,mp_roughneck,mp_shipbreaker", ",");
    names = strTok("Lockdown,Bootleg,Mission,Carbon,Dome,Downturn,Hardhat,Interchange,Fallen,Bakaara,Resistance,Arkaden,Outpost,Seatown,Underground,Village,Liberation,Piazza,Overwatch,Black Box,Sanctuary,Foundation,Oasis,Aground,Erosion,Getaway,Lookout,Terminal,Intersection,U-Turn,Vortex,Gulch,Boardwalk,Parish,Off Shore,Decommission", ",");
    have = getDvar("dcac_maps");
    m = [];
    m["key"] = [];
    m["name"] = [];
    m["pack"] = [];
    m["pack_name"] = strTok("Original Maps,DLC Maps", ",");
    for (i = 0; i < keys.size; i++)
    {
        // without the list (older offline script), the 16 original maps
        if ((have == "" && i >= 16) || (have != "" && !isSubStr("," + have + ",", "," + keys[i] + ",")))
            continue;
        m["key"][m["key"].size] = keys[i];
        m["name"][m["name"].size] = names[i];
        if (i < 16) m["pack"][m["pack"].size] = "0";
        else m["pack"][m["pack"].size] = "1";
    }
    return m;
}

indexOf(list, value)
{
    for (i = 0; i < list.size; i++)
        if (list[i] == value)
            return i;
    return 0;
}

openMatchMenu(index)
{
    self endon("disconnect");
    self endon("death");

    if (isDefined(index)) self.cac_startIndex = index;

    modes = matchModes();
    maps = matchMaps();
    if (!isDefined(self.mm_mode))
    {
        // start from what is running now
        self.mm_mode = indexOf(modes["gt"], level.gameType);
        self.mm_map = indexOf(maps["key"], getDvar("mapname"));
        self.mm_time = getDvar("dcac_opt_timelimit");
        if (self.mm_time == "") self.mm_time = "" + getDvarInt("scr_" + level.gameType + "_timelimit");
        self.mm_score = getDvar("dcac_opt_score");
        if (self.mm_score == "") self.mm_score = "1";
    }

    items = [];
    items[0] = "Mode: " + modes["name"][self.mm_mode];
    items[1] = "Map: " + maps["name"][self.mm_map];
    if (self.mm_time == "0") items[2] = "Time Limit: Unlimited";
    else items[2] = "Time Limit: " + self.mm_time + " min";
    items[3] = "Score Limit: " + scoreName(self.mm_score);
    items[4] = "Start Match";

    d = [];
    d[0] = "Which game mode to play next.";
    d[1] = "Which map to play next.";
    d[2] = "How long a match lasts.";
    d[3] = "How many points win the match.";
    d[4] = "Load mode and map. Limits alone apply instantly.";
    self.cac_descs = d;
    // shown like MW3's Esc menu, with the mode as the right title. The box is like its Maps screen, with the map's
    // preview (its ui_mp picture, shipped in z_deckops_maps.iwd since ui_mp isn't loaded in a match)
    self.cac_map = [];
    self.cac_map["pic"] = "preview_" + maps["key"][self.mm_map] + "_lobby";
    self.cac_map["name"] = maps["name"][self.mm_map];
    self.cac_map["mode"] = modes["name"][self.mm_mode];
    result = self showMenu("MAP / MODE", items, "");
    switch (result)
    {
        case 0:
            r = self pickItem(modes["name"], self.mm_mode);
            if (r != -1) self.mm_mode = r;
            self thread openMatchMenu(0);
            break;
        case 1:
            r = self pickMap(maps, self.mm_map);
            if (r != -1) self.mm_map = r;
            self thread openMatchMenu(1);
            break;
        case 2: self thread pickTimeLimit(); break;
        case 3: self thread pickScoreLimit(); break;
        case 4: self thread startMatch(); break;
        default:
            self.mm_mode = undefined;
            self thread openHubMenu(2);
            break;
    }
}

// Map packs first (original, DLC) when DLC maps are installed, else the maps straight away
pickMap(maps, current)
{
    self endon("disconnect");
    self endon("death");

    packs = [];
    for (i = 0; i < maps["pack"].size; i++)
        if (indexOf(packs, maps["pack"][i]) == 0 && (packs.size == 0 || packs[0] != maps["pack"][i]))
            packs[packs.size] = maps["pack"][i];
    pack = maps["pack"][current];
    for (;;)
    {
        if (packs.size > 1)
        {
            names = [];
            for (i = 0; i < packs.size; i++)
                names[i] = maps["pack_name"][int(packs[i])];
            p = self pickItem(names, indexOf(packs, pack));
            if (p == -1)
                return -1;
            pack = packs[p];
        }
        idx = [];
        names = [];
        for (i = 0; i < maps["key"].size; i++)
            if (maps["pack"][i] == pack)
            {
                idx[idx.size] = i;
                names[names.size] = maps["name"][i];
            }
        r = self pickItem(names, indexOf(idx, current));
        if (r != -1)
            return idx[r];
        if (packs.size <= 1)
            return -1;
    }
}

// Paged list, returns the picked index or -1. 15 rows fit above the prompt, so every Create-a-Class list
// fits on one page (no More page). Only a longer list pages with More
pickItem(names, current, title)
{
    self endon("disconnect");
    self endon("death");

    if (!isDefined(title)) title = "CHOOSE";
    page = 0;
    if (current > 0 && names.size > 15) page = int(current / 14);
    for (;;)
    {
        if (names.size <= 15) first = 0;
        else first = page * 14;
        rows = [];
        per = 14;
        if (names.size <= 15) per = 15;
        for (i = first; i < names.size && i < first + per; i++)
            rows[rows.size] = names[i];
        more = first + per < names.size;
        if (more) rows[rows.size] = "More";
        else if (page > 0) rows[rows.size] = "Back to Start";
        if (current >= first && current < first + per) self.cac_startIndex = current - first;
        result = self showMenu(title, rows, "");
        if (result == -1)
            return -1;
        if (first + result < names.size && result < per)
            return first + result;
        if (more) page++;
        else page = 0;
    }
}

scoreName(mult)
{
    if (mult == "0") return "Unlimited";
    if (mult == "0.5") return "Half";
    if (mult == "2") return "Double";
    return "Default";
}

pickTimeLimit()
{
    self endon("disconnect");
    self endon("death");

    vals = strTok("0,5,10,15,20,30", ",");
    names = strTok("Unlimited,5 min,10 min,15 min,20 min,30 min", ",");
    result = self showMenu("TIME LIMIT", names, "");
    if (result != -1) self.mm_time = vals[result];
    self thread openMatchMenu(2);
}

pickScoreLimit()
{
    self endon("disconnect");
    self endon("death");

    // relative to the mode's DSR default, captured before any override
    mult = strTok("0,0.5,1,2", ",");
    names = strTok("Unlimited,Half,Default,Double", ",");
    result = self showMenu("SCORE LIMIT", names, "");
    if (result != -1) self.mm_score = mult[result];
    self thread openMatchMenu(3);
}

startMatch()
{
    self endon("disconnect");

    modes = matchModes();
    maps = matchMaps();
    setDvar("dcac_opt_timelimit", self.mm_time);
    setDvar("dcac_opt_score", self.mm_score);
    sameMatch = modes["gt"][self.mm_mode] == level.gameType && maps["key"][self.mm_map] == getDvar("mapname");
    self cacCleanup();

    if (sameMatch)
    {
        // only the limits changed: apply live, no restart
        level thread applyMatchOptions();
        self iPrintLnBold("^2Match settings applied");
        self.mm_mode = undefined;
        return;
    }

    rot = "dsr " + modes["dsr"][self.mm_mode] + " map " + maps["key"][self.mm_map];
    self.mm_mode = undefined;
    setDvar("sv_maprotation", rot);
    setDvar("sv_maprotationcurrent", rot);
    iPrintLnBold("^2Loading ^7" + maps["name"][self.mm_map] + " ^2- ^7" + modes["name"][indexOf(modes["dsr"], strTok(rot, " ")[1])]);
    wait 2;
    exitLevel(false);
}

// --- BOT WARFARE (Bot Warfare reads these dvars live)

openBotMenu(index)
{
    self endon("disconnect");
    self endon("death");

    if (isDefined(index)) self.cac_startIndex = index;

    items = [];
    // bots_manage_fill counts the player too
    bots = getDvarInt("bots_manage_fill") - 1;
    if (bots < 0) bots = 0;
    items[0] = "Bot Count: " + bots;
    items[1] = "Difficulty: " + botSkillName(getDvarInt("bots_skill"));
    if (getDvar("bots_team") == "autoassign" || getDvar("bots_team") == "") items[2] = "Bot Team: Balanced";
    else items[2] = "Bot Team: All Enemies";
    items[3] = "Play Objective: " + onOff(botSetting("bots_play_obj"));
    items[4] = "Camping: " + onOff(botSetting("bots_play_camp"));
    items[5] = "Killstreaks: " + onOff(botSetting("bots_play_killstreak"));
    items[6] = "Take Care Packages: " + onOff(botSetting("bots_play_take_carepackages"));
    items[7] = "Jump & Dropshot: " + onOff(botSetting("bots_play_jumpdrop"));
    if (getDvarInt("bots_loadout_allow_op")) items[8] = "Bot Classes: Anything Goes";
    else items[8] = "Bot Classes: Sensible";
    // Bot Warfare reads bots_main_chat per message as a chattiness multiplier
    c = getDvarFloat("bots_main_chat");
    if (c <= 0) items[9] = "Bot Chat: Off";
    else if (c < 2) items[9] = "Bot Chat: Normal";
    else items[9] = "Bot Chat: Chatty";

    d = [];
    d[0] = "How many bots are in the match (0 to 12).";
    d[1] = "How well bots aim and react. Mixed = all levels.";
    d[2] = "Balanced: bots on both sides. All Enemies: vs you.";
    d[3] = "Bots go for flags, bombs and capture points.";
    d[4] = "Bots sometimes hold a spot and wait for you.";
    d[5] = "Bots call in their own killstreaks.";
    d[6] = "Bots run to and grab care packages.";
    d[7] = "Bots jump and drop prone during gunfights.";
    d[8] = "Sensible: normal classes. Anything Goes: OP too.";
    d[9] = "Bots type in chat. Chatty means they talk more.";
    self.cac_descs = d;
    result = self showMenu("BOT WARFARE", items, "");
    switch (result)
    {
        case 0: self thread pickBotCount(); break;
        case 1: self thread pickBotSkill(); break;
        case 2:
            if (getDvar("bots_team") == "autoassign" || getDvar("bots_team") == "")
            {
                // every bot on the team opposite the player
                if (self.team == "axis") setDvar("bots_team", "allies");
                else setDvar("bots_team", "axis");
                setDvar("bots_team_force", "1");
            }
            else
            {
                setDvar("bots_team", "autoassign");
                setDvar("bots_team_force", "0");
            }
            self thread openBotMenu(2);
            break;
        case 3: botToggle("bots_play_obj"); self thread openBotMenu(3); break;
        case 4: botToggle("bots_play_camp"); self thread openBotMenu(4); break;
        case 5: botToggle("bots_play_killstreak"); self thread openBotMenu(5); break;
        case 6: botToggle("bots_play_take_carepackages"); self thread openBotMenu(6); break;
        case 7: botToggle("bots_play_jumpdrop"); self thread openBotMenu(7); break;
        case 8:
            if (getDvarInt("bots_loadout_allow_op"))
            {
                setDvar("bots_loadout_allow_op", "0");
                setDvar("bots_loadout_reasonable", "1");
            }
            else
            {
                setDvar("bots_loadout_allow_op", "1");
                setDvar("bots_loadout_reasonable", "0");
            }
            self thread openBotMenu(8);
            break;
        case 9:
            c = getDvarFloat("bots_main_chat");
            if (c <= 0) setDvar("bots_main_chat", "1");
            else if (c < 2) setDvar("bots_main_chat", "3");
            else setDvar("bots_main_chat", "0");
            self thread openBotMenu(9);
            break;
        default: self thread openHubMenu(3); break;
    }
}

onOff(v)
{
    if (v) return "On";
    return "Off";
}

// While the menu is open botsPause holds some bots_play_* at 0 and restores them on close,
// so read and change the value it will restore, not the live one
botSetting(dvar)
{
    if (isDefined(level.dcac_botplay) && isDefined(level.dcac_botplay[dvar]))
        return int(level.dcac_botplay[dvar]);
    return getDvarInt(dvar);
}

botToggle(dvar)
{
    if (botSetting(dvar)) v = "0";
    else v = "1";
    if (isDefined(level.dcac_botplay) && isDefined(level.dcac_botplay[dvar]))
        level.dcac_botplay[dvar] = v;
    else
        setDvar(dvar, v);
}

pickBotCount()
{
    self endon("disconnect");
    self endon("death");

    // sv_maxclients is 13 in the LAN config: 12 bots + the player (fill counts the player too)
    counts = strTok("0,2,4,6,8,10,12", ",");
    result = self showMenu("BOT COUNT", counts, "");
    if (result != -1)
    {
        fill = int(counts[result]);
        if (fill > 0) fill++;
        setDvar("bots_manage_fill", "" + fill);
    }
    self thread openBotMenu(0);
}

pickBotSkill()
{
    self endon("disconnect");
    self endon("death");

    skills = strTok("0,1,3,5,7", ",");
    names = [];
    for (i = 0; i < skills.size; i++)
        names[i] = botSkillName(int(skills[i]));
    result = self showMenu("DIFFICULTY", names, "");
    if (result != -1)
        setDvar("bots_skill", skills[result]);
    self thread openBotMenu(1);
}

botSkillName(n)
{
    if (n == 0) return "Mixed";
    if (n <= 2) return "Easy";
    if (n <= 4) return "Normal";
    if (n <= 6) return "Hard";
    return "Veteran";
}

// --- MAIN MENU

classItems()
{
    items = [];
    for (n = 0; n < 5; n++)
    {
        items[n] = "Class " + (n + 1) + ": " + cacName(self.dcac[n]["loadoutPrimary"]);
        if (isDefined(self.dcac_use) && self.dcac_use == n)
            items[n] += " (in use)";
    }
    return items;
}

openClassList(index)
{
    self endon("disconnect");
    self endon("death");

    if (!isDefined(index) && isDefined(self.dcac_use)) index = self.dcac_use;
    if (isDefined(index)) self.cac_startIndex = index;
    result = self showMenu("CLASS EDITOR", self classItems(), "");
    if (result == -1) { self thread openHubMenu(0); return; }
    self.dcac_cur = result;
    self thread openCACMenu();
}

openCACMenu()
{
    self endon("disconnect");
    self endon("death");


    items = [];
    items[0] = "Primary Weapon";
    items[1] = "Primary Proficiency";
    items[2] = "Secondary Weapon";
    items[3] = "Perk 1 (Blue)";
    items[4] = "Perk 2 (Red)";
    items[5] = "Perk 3 (Yellow)";
    items[6] = "Equipment";
    items[7] = "Deathstreak";
    items[8] = "Strike Package";
    items[9] = "Use This Class";

    d = [];
    d[9] = "Switch to this class now, or on your next spawn.";
    self.cac_descs = d;
    result = self showMenu("CLASS " + (self.dcac_cur + 1), items, "");

    if (result == -1) { self thread openClassList(self.dcac_cur); return; }


    switch (result)
    {
        case 0: self thread pickPrimaryCategory(0); break;
        case 1: self thread pickProficiency(0); break;
        case 2: self thread pickSecondaryCategory(); break;
        case 3: self thread pickPerk(1); break;
        case 4: self thread pickPerk(2); break;
        case 5: self thread pickPerk(3); break;
        case 6: self thread pickEquipmentMenu(); break;
        case 7: self thread pickDeathstreak(); break;
        case 8: self thread pickStreakType(); break;
        case 9: self thread applyLoadout(); break;
    }
}

// --- PRIMARY WEAPON FLOW

pickPrimaryCategory(slot)
{
    if (!isDefined(slot)) slot = 0;

    self endon("disconnect");
    self endon("death");

    items = [];
    for (i = 0; i < level.cac["primary_cats"].size; i++)
        items[i] = level.cac["primary_cats"][i];

    title = "PRIMARY - CATEGORY";
    if (slot == 1) title = "OVERKILL - CATEGORY";
    result = self showMenu(title, items, "");
    if (result == -1) { self thread openCACMenu(); return; }

    switch (result)
    {
        case 0: self thread pickWeaponFromList("ar", "ar_name", slot); break;
        case 1: self thread pickWeaponFromList("smg", "smg_name", slot); break;
        case 2: self thread pickWeaponFromList("lmg", "lmg_name", slot); break;
        case 3: self thread pickWeaponFromList("sniper", "sniper_name", slot); break;
        case 4: self thread pickWeaponFromList("shotgun", "shotgun_name", slot); break;
        case 5:
            if (true)
            {
                self cacSet(wKey(slot, "weapon"), "riotshield");
                self cacSet(wKey(slot, "attachment" + 0), "none");
                self cacSet(wKey(slot, "attachment" + 1), "none");
                self cacSet(wKey(slot, "buff"), "specialty_null");
                self iPrintLnBold("^2Weapon set: ^7Riot Shield");
            }
            else
                self iPrintLnBold("^1Riot Shield not unlocked yet");
            self thread openCACMenu();
            break;
    }
}

pickWeaponFromList(listKey, nameKey, weaponSlot)
{
    self endon("disconnect");
    self endon("death");

    unlocked = self getUnlockedItems(listKey, nameKey);

    if (unlocked["names"].size == 0)
    {
        self iPrintLnBold("^1No weapons unlocked in this category");
        if (weaponSlot == 0) self thread pickPrimaryCategory(0);
        else self thread pickSecondaryCategory();
        return;
    }

    title = "PICK WEAPON";
    if (weaponSlot == 1) title = "PICK SECONDARY";

    result = self showMenu(title, unlocked["names"], "");
    if (result == -1)
    {
        if (weaponSlot == 0) self thread pickPrimaryCategory(0);
        else self thread pickSecondaryCategory();
        return;
    }

    weapon = unlocked["keys"][result];

    self cacSet(wKey(weaponSlot, "weapon"), weapon);
    self cacSet(wKey(weaponSlot, "attachment" + 0), "none");
    self cacSet(wKey(weaponSlot, "attachment" + 1), "none");
    self cacSet(wKey(weaponSlot, "buff"), "specialty_null");
    self iPrintLnBold("^2Weapon set: ^7" + unlocked["names"][result]);

    self thread pickAttachment(weapon, weaponSlot, 0);
}

// --- SECONDARY WEAPON FLOW

pickSecondaryCategory()
{
    self endon("disconnect");
    self endon("death");

    // Overkill: the secondary slot takes a primary weapon instead
    if (self cacGet("loadoutPerk2") == "specialty_twoprimaries")
    {
        self thread pickPrimaryCategory(1);
        return;
    }

    items = [];
    for (i = 0; i < level.cac["secondary_cats"].size; i++)
        items[i] = level.cac["secondary_cats"][i];

    result = self showMenu("SECONDARY - CATEGORY", items, "");
    if (result == -1) { self thread openCACMenu(); return; }

    switch (result)
    {
        case 0: self thread pickWeaponFromList("machpistol", "machpistol_name", 1); break;
        case 1: self thread pickWeaponFromList("hg", "hg_name", 1); break;
        case 2: self thread pickWeaponFromList("launcher", "launcher_name", 1); break;
    }
}

// --- ATTACHMENT PICKER (per weapon)

// Valid attachments per weapon come from the game's own mp/statsTable.csv (columns 11+), the same
// source as MW3's Create-a-Class and Bot Warfare. Codes are class-specific (silencer02 on pistols,
// silencer03 on shotguns, m320/gp25 launchers). Generic codes build weapons that don't exist.
getAttachmentsForGun(gun)
{
    row = tableLookupRowNum("mp/statsTable.csv", 4, gun);
    atts = [];
    if (row < 0)
        return atts;
    for (h = 0; h < 10; h++)
    {
        a = tableLookupByRow("mp/statsTable.csv", row, h + 11);
        if (a == "")
            break;
        atts[atts.size] = a;
    }
    return atts;
}

// Pair rules from the game's mp/attachmentCombos.csv
isValidAttachmentCombo(att1, att2)
{
    if (att1 == "none" || att2 == "none")
        return true;
    if (att1 == att2)
        return false;
    col = tableLookupRowNum("mp/attachmentCombos.csv", 0, att1);
    return tableLookup("mp/attachmentCombos.csv", 0, att2, col) != "no";
}

gunHasAttachment(gun, att)
{
    atts = getAttachmentsForGun(gun);
    for (i = 0; i < atts.size; i++)
        if (atts[i] == att)
            return true;
    return false;
}

pickAttachment(weapon, weaponSlot, attachSlot)
{
    self endon("disconnect");
    self endon("death");

    first = self cacGet(wKey(weaponSlot, "attachment0"));
    atts = getAttachmentsForGun(weapon);
    keys = [];
    names = [];
    keys[0] = "none";
    names[0] = "No Attachment";
    for (i = 0; i < atts.size; i++)
    {
        if (attachSlot == 1 && !isValidAttachmentCombo(first, atts[i]))
            continue;
        keys[keys.size] = atts[i];
        names[names.size] = cacName(atts[i]);
    }

    // riot shield, launchers: nothing to pick
    if (keys.size <= 1)
    {
        self thread openCACMenu();
        return;
    }

    result = self pickItem(names, indexOf(keys, self cacGet(wKey(weaponSlot, "attachment" + attachSlot))), "ATTACHMENT " + (attachSlot + 1));
    if (result == -1)
    {
        self thread openCACMenu();
        return;
    }

    attach = keys[result];
    self cacSet(wKey(weaponSlot, "attachment" + attachSlot), attach);
    if (attachSlot == 0 && attach == "none")
        self cacSet(wKey(weaponSlot, "attachment1"), "none");
    // a new first attachment can clash with the second one
    if (attachSlot == 0 && !isValidAttachmentCombo(attach, self cacGet(wKey(weaponSlot, "attachment1"))))
        self cacSet(wKey(weaponSlot, "attachment1"), "none");

    // Attachments proficiency on the primary allows a second attachment
    if (attachSlot == 0 && attach != "none" && weaponSlot == 0 && self cacGet(wKey(0, "buff")) == "specialty_bling")
        self thread pickAttachment(weapon, weaponSlot, 1);
    else
        self thread openCACMenu();
}

// --- PROFICIENCY PICKER (per weapon class)

pickProficiency(weaponSlot)
{
    self endon("disconnect");
    self endon("death");

    weapon = self cacGet(wKey(weaponSlot, "weapon"));

    if (!isDefined(level.cac["wep_prof_type"][weapon]))
    {
        self iPrintLnBold("^1No proficiencies for this weapon");
        self thread openCACMenu();
        return;
    }

    profType = level.cac["wep_prof_type"][weapon];
    profListKey = "prof_" + profType;
    profNameKey = "prof_" + profType + "_name";

    unlocked = self getUnlockedProficiencies(weapon, profListKey, profNameKey);

    if (unlocked["names"].size == 0)
    {
        self iPrintLnBold("^1No proficiencies unlocked");
        self thread openCACMenu();
        return;
    }

    result = self showMenu("PROFICIENCY", unlocked["names"], "");
    if (result == -1) { self thread openCACMenu(); return; }

    prof = unlocked["keys"][result];
    self cacSet(wKey(weaponSlot, "buff"), prof);
    self iPrintLnBold("^2Proficiency set: ^7" + unlocked["names"][result]);

    // Attachments proficiency unlocks a second attachment: offer it right away
    if (prof == "specialty_bling")
    {
        self thread pickAttachment(weapon, weaponSlot, 1);
        return;
    }
    self cacSet(wKey(weaponSlot, "attachment" + 1), "none");

    self thread openCACMenu();
}

// --- PERK PICKER

pickPerk(perkSlot)
{
    self endon("disconnect");
    self endon("death");

    listKey = "perk" + perkSlot;
    nameKey = "perk" + perkSlot + "_name";

    unlocked = self getUnlockedItems(listKey, nameKey);

    if (unlocked["names"].size == 0)
    {
        self iPrintLnBold("^1No perks unlocked in this slot");
        self thread openCACMenu();
        return;
    }

    slotNames = [];
    slotNames[1] = "PERK 1 (BLUE)";
    slotNames[2] = "PERK 2 (RED)";
    slotNames[3] = "PERK 3 (YELLOW)";

    result = self showMenu(slotNames[perkSlot], unlocked["names"], "");
    if (result == -1) { self thread openCACMenu(); return; }

    perk = unlocked["keys"][result];
    self cacSet(perkKey(perkSlot), perk);

    // Without Overkill the secondary takes no proficiency, so clear it
    if (perkSlot == 2)
    {
        if (perk != "specialty_twoprimaries")
        {
            self cacSet(wKey(1, "buff"), "specialty_null");
            // dropping Overkill: a primary in the secondary slot goes back to a pistol
            if (isPrimaryWeapon(self cacGet("loadoutSecondary")))
            {
                self cacSet(wKey(1, "weapon"), "iw5_usp45");
                self cacSet(wKey(1, "attachment0"), "none");
                self cacSet(wKey(1, "attachment1"), "none");
            }
        }
    }

    self iPrintLnBold("^2Perk " + perkSlot + " set: ^7" + unlocked["names"][result]);
    self thread openCACMenu();
}

// --- EQUIPMENT, TACTICAL, DEATHSTREAK

pickEquipmentMenu()
{
    self endon("disconnect");
    self endon("death");

    items = [];
    items[0] = "Lethal";
    items[1] = "Tactical";
    result = self showMenu("EQUIPMENT", items, "");
    switch (result)
    {
        case 0: self thread pickEquipment(); break;
        case 1: self thread pickTactical(); break;
        default: self thread openCACMenu(); break;
    }
}

pickEquipment()
{
    self endon("disconnect");
    self endon("death");

    unlocked = self getUnlockedItems("equip", "equip_name");

    if (unlocked["names"].size == 0)
    {
        self iPrintLnBold("^1No equipment unlocked");
        self thread openCACMenu();
        return;
    }

    result = self showMenu("EQUIPMENT", unlocked["names"], "");
    if (result == -1) { self thread pickEquipmentMenu(); return; }

    self cacSet(perkKey(0), unlocked["keys"][result]);
    self iPrintLnBold("^2Equipment set: ^7" + unlocked["names"][result]);
    self thread pickEquipmentMenu();
}

pickTactical()
{
    self endon("disconnect");
    self endon("death");

    // Tacticals are always unlocked
    items = [];
    for (i = 0; i < level.cac["tactical"].size; i++)
        items[i] = level.cac["tactical_name"][i];

    result = self showMenu("TACTICAL", items, "");
    if (result == -1) { self thread pickEquipmentMenu(); return; }

    self cacSet(perkKey(6), level.cac["tactical"][result]);
    self iPrintLnBold("^2Tactical set: ^7" + level.cac["tactical_name"][result]);
    self thread pickEquipmentMenu();
}

pickDeathstreak()
{
    self endon("disconnect");
    self endon("death");

    // Deathstreaks: the full list (offline, nothing is locked)
    unlocked = self getUnlockedItems("deathstreak", "deathstreak_name");

    if (unlocked["names"].size == 0)
    {
        self iPrintLnBold("^1No deathstreaks unlocked");
        self thread openCACMenu();
        return;
    }

    result = self showMenu("DEATHSTREAK", unlocked["names"], "");
    if (result == -1) { self thread openCACMenu(); return; }

    self cacSet("loadoutDeathstreak", unlocked["keys"][result]);
    self iPrintLnBold("^2Deathstreak set: ^7" + unlocked["names"][result]);
    self thread openCACMenu();
}

isPrimaryWeapon(w)
{
    if (w == "riotshield")
        return true;
    lists = strTok("ar,smg,lmg,sniper,shotgun", ",");
    for (l = 0; l < lists.size; l++)
        for (i = 0; i < level.cac[lists[l]].size; i++)
            if (level.cac[lists[l]][i] == w)
                return true;
    return false;
}

// --- STRIKE PACKAGE

pickStreakType()
{
    self endon("disconnect");
    self endon("death");

    result = self showMenu("STRIKE PACKAGE", level.cac["streaktypes_name"], "");
    if (result == -1) { self thread openCACMenu(); return; }

    self cacSet("loadoutStreakType", level.cac["streaktypes"][result]);
    self cacSet("loadoutKillstreak1", "none");
    self cacSet("loadoutKillstreak2", "none");
    self cacSet("loadoutKillstreak3", "none");
    self thread pickStreak(1);
}

// Streaks are stored by kill cost (setKillstreaks in _class.gsc), so two with the same cost
// would overwrite each other. Specialist costs are the slot (2/4/6) instead.
pickStreak(n)
{
    self endon("disconnect");
    self endon("death");

    type = getSubStr(self cacGet("loadoutStreakType"), 11);
    list = level.cac["ks_" + type];
    names = level.cac["ks_" + type + "_name"];

    keys = [];
    items = [];
    for (i = 0; i < list.size; i++)
    {
        ks = list[i];
        taken = false;
        for (k = 1; k < n; k++)
        {
            other = self cacGet("loadoutKillstreak" + k);
            if (other == ks)
                taken = true;
            else if (type != "specialist" && self maps\mp\killstreaks\_killstreaks::getStreakCost(other) == self maps\mp\killstreaks\_killstreaks::getStreakCost(ks))
                taken = true;
        }
        if (taken)
            continue;
        keys[keys.size] = ks;
        if (type == "specialist")
            items[items.size] = names[i] + " (" + (n * 2) + ")";
        else
            items[items.size] = names[i] + " (" + self maps\mp\killstreaks\_killstreaks::getStreakCost(ks) + ")";
    }

    result = self pickItem(items, indexOf(keys, self cacGet("loadoutKillstreak" + n)), "KILLSTREAK " + n);
    if (result == -1) { self thread pickStreakType(); return; }

    self cacSet("loadoutKillstreak" + n, keys[result]);
    if (n < 3) self thread pickStreak(n + 1);
    else self thread openCACMenu();
}

// Infected, Gun Game, One in the Chamber and the Juggernaut modes hand out their own loadouts
cacModeOwnsLoadout()
{
    switch (level.gameType)
    {
        case "infect":
        case "gun":
        case "oic":
        case "jugg":
        case "tjugg":
            return true;
    }
    return false;
}

// The gamemode class skips MW3's checks, so anything invalid falls back here instead of an empty hand
cacSanitize()
{
    p = self cacGet("loadoutPrimary");
    if (!maps\mp\gametypes\_class::isValidPrimary(p, false))
    {
        self cacSet("loadoutPrimary", "iw5_m4");
        p = "iw5_m4";
    }
    sec = self cacGet("loadoutSecondary");
    if (sec != "none" && !maps\mp\gametypes\_class::isValidSecondary(sec, self cacGet("loadoutPerk2"), self cacGet("loadoutPerk3"), false))
        self cacSet("loadoutSecondary", "iw5_usp45");

    slots = strTok("loadoutPrimary,loadoutSecondary", ",");
    for (s = 0; s < slots.size; s++)
    {
        w = self cacGet(slots[s]);
        a = strTok(slots[s] + "Attachment," + slots[s] + "Attachment2", ",");
        if (!isValidAttachmentCombo(self cacGet(a[0]), self cacGet(a[1])))
            self cacSet(a[1], "none");
        for (i = 0; i < a.size; i++)
        {
            att = self cacGet(a[i]);
            if (att != "none" && (!gunHasAttachment(w, att) || !maps\mp\gametypes\_class::isValidCombination(w, att)))
                self cacSet(a[i], "none");
        }
    }
}

// --- APPLY LOADOUT (Divity's class swap trick)

applyLoadout()
{
    self endon("disconnect");
    self endon("death");

    self cacCleanup();

    self cacSanitize();
    self cacSetUse(self.dcac_cur);
    self dlog("use class " + self.dcac_cur);

    // MW3's own rule: right away only in the spawn grace period before any combat (no ammo refills),
    // else class "gamemode" gives it next spawn
    if (level.ingraceperiod && !self.hasdonecombat)
    {
        self useCacLoadout();
        self iPrintLnBold("^2Class " + (self.dcac_cur + 1) + " equipped");
        return;
    }
    self.pers["gamemodeLoadout"] = self.dcac[self.dcac_use];
    self.pers["class"] = "gamemode";
    self.pers["lastClass"] = "";
    self iPrintLnBold(game["strings"]["change_class"]);
}

// Gives the class in use now
useCacLoadout()
{
    edit = self.dcac_cur;
    self.dcac_cur = self.dcac_use;
    self cacSanitize();
    self.dcac_cur = edit;
    self.pers["gamemodeLoadout"] = self.dcac[self.dcac_use];
    self.pers["class"] = "gamemode";
    self.pers["lastClass"] = "";
    self.class = "gamemode";
    self.lastClass = "";
    self maps\mp\gametypes\_class::giveLoadout(self.team, "gamemode");
}

// A map change clears self.pers and MW3 auto-picks class0 on join, so put the class in use back on spawn.
// The first spawn of a map opens the class pick (MW3 shows no class list on joining a LAN server).
watchSpawnLoadout()
{
    self endon("disconnect");
    first = true;
    for (;;)
    {
        self waittill("spawned_player");
        self dlog("spawn class=" + self.class + " use=" + getDvar("dcac_use_" + self.guid));
        if (isDefined(self.dcac_use) && self.class != "gamemode" && !cacModeOwnsLoadout())
            self useCacLoadout();
        if (first && !cacModeOwnsLoadout())
            self thread openJoinPicker();
        first = false;
    }
}

// Class pick on joining, like BO1's: the five DeckOps classes. MW3's own Choose Class popup answers class0 at
// once (our zone), so the player is already spawned (class in use or class0) and picks over it before any combat.
openJoinPicker()
{
    self endon("disconnect");
    self endon("death");
    wait 0.2;
    if (self.cac_open)
        return;
    self.cac_open = true;
    for (;;)
    {
        items = self classItems();
        if (isDefined(self.dcac_use))
        {
            self.dcac_cur = self.dcac_use;
            self.cac_startIndex = self.dcac_use;
        }
        r = self showMenu("CHOOSE CLASS", items, "");
        // a class has to be picked, as in MW3's own list
        if (r != -1)
            break;
    }
    self cacCleanup();
    self.dcac_cur = r;
    self cacSetUse(r);
    // Just spawned and held in the menu: given now, unless the player already fought
    if (!self.hasdonecombat)
        self useCacLoadout();
    else
    {
        self.pers["gamemodeLoadout"] = self.dcac[r];
        self.pers["class"] = "gamemode";
        self.pers["lastClass"] = "";
        self iPrintLnBold(game["strings"]["change_class"]);
    }
}

// --- GENERIC MENU (same layout as the WaW / BO1 / BO2 menus, MW3 green)

// Retail MW3 strike packages (valid lists in _class.gsc also hold cut streaks, left out here).
// Specialist uses the perks as "<perk>_ks". Their cost is the slot (2/4/6) via getStreakCost.
buildStreakData()
{
    level.cac["ks_assault"] = strTok("uav,airdrop_assault,ims,predator_missile,airdrop_sentry_minigun,precision_airstrike,helicopter,littlebird_flock,littlebird_support,remote_mortar,airdrop_remote_tank,ac130,helicopter_flares,airdrop_juggernaut,osprey_gunner", ",");
    level.cac["ks_assault_name"] = strTok("UAV,Care Package,I.M.S.,Predator Missile,Sentry Gun,Precision Airstrike,Attack Helicopter,Strafe Run,AH-6 Overwatch,Reaper,Assault Drone,AC-130,Pave Low,Juggernaut,Osprey Gunner", ",");
    level.cac["ks_support"] = strTok("uav_support,counter_uav,deployable_vest,airdrop_trap,sam_turret,remote_uav,triple_uav,remote_mg_turret,stealth_airstrike,airdrop_juggernaut_recon,escort_airdrop,emp", ",");
    level.cac["ks_support_name"] = strTok("UAV,Counter-UAV,Ballistic Vests,Airdrop Trap,SAM Turret,Recon Drone,Advanced UAV,Remote Sentry,Stealth Bomber,Juggernaut Recon,Escort Airdrop,EMP", ",");

    level.cac["ks_specialist"] = [];
    level.cac["ks_specialist_name"] = [];
    lists = strTok("perk1,perk2,perk3", ",");
    for (l = 0; l < lists.size; l++)
        for (i = 0; i < level.cac[lists[l]].size; i++)
        {
            perk = level.cac[lists[l]][i];
            if (perk == "specialty_twoprimaries")
                continue;
            level.cac["ks_specialist"][level.cac["ks_specialist"].size] = perk + "_ks";
            level.cac["ks_specialist_name"][level.cac["ks_specialist_name"].size] = level.cac[lists[l] + "_name"][i];
        }

    level.cac["streaktypes"] = strTok("streaktype_assault,streaktype_support,streaktype_specialist", ",");
    level.cac["streaktypes_name"] = strTok("Assault,Support,Specialist", ",");
}

// Code name -> display name: dcacCatalog() has the game's names, plus every list with a "_name" list
// (strike packages, Specialist)
buildNameLookup()
{
    keys = getArrayKeys(level.cac);
    for (k = 0; k < keys.size; k++)
    {
        if (!isDefined(level.cac[keys[k] + "_name"]))
            continue;
        for (i = 0; i < level.cac[keys[k]].size; i++)
            level.cac_names[level.cac[keys[k]][i]] = level.cac[keys[k] + "_name"][i];
    }
}

cacName(code)
{
    if (!isDefined(code) || code == "none" || code == "specialty_null")
        return "None";
    if (isDefined(level.cac_names[code]))
        return level.cac_names[code];
    return code;
}

// Bots hold still while anyone has the menu open (Bot Warfare reads bots_play_* live)
botsPause()
{
    if (!isDefined(level.dcac_menus)) level.dcac_menus = 0;
    level.dcac_menus++;
    if (level.dcac_menus > 1)
        return;
    level.dcac_botplay = [];
    dvars = strTok("bots_play_move,bots_play_fire,bots_play_knife,bots_play_nade,bots_play_killstreak", ",");
    for (i = 0; i < dvars.size; i++)
    {
        level.dcac_botplay[dvars[i]] = getDvar(dvars[i]);
        setDvar(dvars[i], "0");
    }
}

botsResume()
{
    if (!isDefined(level.dcac_menus) || level.dcac_menus <= 0)
        return;
    level.dcac_menus--;
    if (level.dcac_menus > 0)
        return;
    keys = getArrayKeys(level.dcac_botplay);
    for (i = 0; i < keys.size; i++)
        setDvar(keys[i], level.dcac_botplay[keys[i]]);
}

// Client dvars only go out when they change: a page sends one reliable command per dvar
cacDvar(name, value)
{
    if (!isDefined(self.dcac_sent)) self.dcac_sent = [];
    if (isDefined(self.dcac_sent[name]) && self.dcac_sent[name] == value)
        return;
    self.dcac_sent[name] = value;
    self setClientDvar(name, value);
}

cacOpenUi()
{
    self botsPause();
    self freezeControlsWrapper(true);
    self setClientDvar("actionSlotsHide", "1");
    self.cac_ui = true;
}

cacUpdatePanel()
{
    l = self.dcac[self.dcac_cur];
    self cacDvar("dcac_cls", "CLASS " + (self.dcac_cur + 1));
    self cacDvar("dcac_pimg", weaponPic(l["loadoutPrimary"]));
    self cacDvar("dcac_p0", cacName(l["loadoutPrimary"]));
    self cacDvar("dcac_p1", cacAttachName(l["loadoutPrimaryAttachment"]));
    p2 = "";
    if (l["loadoutPrimaryAttachment2"] != "none") p2 = cacName(l["loadoutPrimaryAttachment2"]);
    self cacDvar("dcac_p2", p2);
    self cacDvar("dcac_p3", cacName(l["loadoutPrimaryBuff"]));
    self cacDvar("dcac_simg", weaponPic(l["loadoutSecondary"]));
    self cacDvar("dcac_s0", cacName(l["loadoutSecondary"]));
    self cacDvar("dcac_s1", cacAttachName(l["loadoutSecondaryAttachment"]));
    s2 = "";
    if (l["loadoutSecondaryAttachment2"] != "none") s2 = cacName(l["loadoutSecondaryAttachment2"]);
    self cacDvar("dcac_s2", s2);
    self cacDvar("dcac_pk0", cacName(l["loadoutPerk1"]));
    self cacDvar("dcac_pk1", cacName(l["loadoutPerk2"]));
    self cacDvar("dcac_pk2", cacName(l["loadoutPerk3"]));
    self cacDvar("dcac_eq0", cacName(l["loadoutEquipment"]));
    self cacDvar("dcac_eq1", cacName(l["loadoutOffhand"]));
    self cacDvar("dcac_ds", cacName(l["loadoutDeathstreak"]));
    self cacDvar("dcac_st", streakTypeLabel(l["loadoutStreakType"]));
    self cacDvar("dcac_ks0", cacName(l["loadoutKillstreak1"]));
    self cacDvar("dcac_ks1", cacName(l["loadoutKillstreak2"]));
    self cacDvar("dcac_ks2", cacName(l["loadoutKillstreak3"]));
}

// MW3's own picture for a weapon (statstable column 6), "" when it has none
weaponPic(w)
{
    if (!isDefined(w) || w == "none")
        return "";
    return tableLookup("mp/statstable.csv", 4, w, 6);
}

streakTypeLabel(t)
{
    if (t == "streaktype_support") return "SUPPORT";
    if (t == "streaktype_specialist") return "SPECIALIST";
    return "ASSAULT";
}

cacAttachName(a)
{
    if (a == "none")
        return "No Attachment";
    return cacName(a);
}

// self.cac_startIndex / self.cac_descs are one-shot inputs (cursor row, row descriptions).
// Fills the dcac_* dvars of our muteplayer menu and reopens it, so its onOpen puts the focus on the start row.
showMenu(title, items, hint)
{
    self endon("disconnect");
    self endon("death");

    if (!isDefined(self.cac_ui))
        self cacOpenUi();

    menuSize = items.size;
    if (menuSize > 15) menuSize = 15;

    // a page redrawn after a change keeps the cursor on the row the player was on
    index = 0;
    if (isDefined(self.cac_startIndex))
    {
        if (self.cac_startIndex < menuSize) index = self.cac_startIndex;
        self.cac_startIndex = undefined;
    }
    descs = self.cac_descs;
    self.cac_descs = undefined;
    mp = self.cac_map;
    self.cac_map = undefined;
    if (!isDefined(mp))
    {
        mp = [];
        mp["pic"] = ""; mp["name"] = ""; mp["mode"] = "";
    }
    self cacDvar("dcac_mpic", mp["pic"]);
    self cacDvar("dcac_mt", mp["name"]);
    self cacDvar("dcac_mu", mp["mode"]);

    self cacDvar("dcac_title", title);
    for (i = 0; i < 15; i++)
    {
        r = "";
        d = "";
        if (i < menuSize) r = items[i];
        if (isDefined(descs) && isDefined(descs[i])) d = descs[i];
        self cacDvar("dcac_r" + i, r);
        self cacDvar("dcac_d" + i, d);
    }
    self cacDvar("dcac_start", "" + index);
    self cacUpdatePanel();
    self closepopupmenu();
    self openpopupmenu("muteplayer");

    for (;;)
    {
        self waittill("menuresponse", menu, response);
        if (menu != "muteplayer")
            continue;
        self dlog("input " + response);
        if (response == "back")
            return -1;
        i = int(response);
        if (i >= 0 && i < menuSize)
            return i;
    }
}

// Generated by gen_catalog.py from MW3's tables, English strings and Create-a-Class menus. Do not edit.
dcacCatalog()
{
    level.cac = [];
    level.cac["primary_cats"] = strTok("Assault Rifles,Sub Machine Guns,Light Machine Guns,Sniper Rifles,Shotguns,Riot Shield", ",");
    level.cac["secondary_cats"] = strTok("Machine Pistols,Handguns,Launchers", ",");
    level.cac["ar"] = strTok("iw5_m4,iw5_m16,iw5_scar,iw5_cm901,iw5_type95,iw5_g36c,iw5_acr,iw5_mk14,iw5_ak47,iw5_fad", ",");
    level.cac["ar_name"] = strTok("M4A1,M16A4,SCAR-L,CM901,Type 95,G36C,ACR 6.8,MK14,AK-47,FAD", ",");
    level.cac["smg"] = strTok("iw5_mp5,iw5_ump45,iw5_pp90m1,iw5_p90,iw5_m9,iw5_mp7", ",");
    level.cac["smg_name"] = strTok("MP5,UMP45,PP90M1,P90,PM-9,MP7", ",");
    level.cac["lmg"] = strTok("iw5_sa80,iw5_mg36,iw5_pecheneg,iw5_mk46,iw5_m60", ",");
    level.cac["lmg_name"] = strTok("L86 LSW,MG36,PKP Pecheneg,MK46,M60E4", ",");
    level.cac["sniper"] = strTok("iw5_barrett,iw5_l96a1,iw5_dragunov,iw5_as50,iw5_rsass,iw5_msr", ",");
    level.cac["sniper_name"] = strTok("Barrett .50cal,L118A,Dragunov,AS50,Rsass,MSR", ",");
    level.cac["shotgun"] = strTok("iw5_usas12,iw5_ksg,iw5_spas12,iw5_aa12,iw5_striker,iw5_1887", ",");
    level.cac["shotgun_name"] = strTok("USAS 12,KSG 12,SPAS-12,AA-12,Striker,Model 1887", ",");
    level.cac["shield"] = strTok("riotshield", ",");
    level.cac["shield_name"] = strTok("Riot Shield", ",");
    level.cac["machpistol"] = strTok("iw5_fmg9,iw5_mp9,iw5_skorpion,iw5_g18", ",");
    level.cac["machpistol_name"] = strTok("FMG9,MP9,Skorpion,G18", ",");
    level.cac["hg"] = strTok("iw5_usp45,iw5_p99,iw5_mp412,iw5_44magnum,iw5_fnfiveseven,iw5_deserteagle", ",");
    level.cac["hg_name"] = strTok("USP .45,P99,MP412,.44 Magnum,Five Seven,Desert Eagle", ",");
    level.cac["launcher"] = strTok("iw5_smaw,javelin,stinger,xm25,rpg", ",");
    level.cac["launcher_name"] = strTok("SMAW,Javelin,Stinger,XM25,RPG-7", ",");
    level.cac["perk1"] = strTok("specialty_paint,specialty_fastreload,specialty_blindeye,specialty_longersprint,specialty_scavenger", ",");
    level.cac["perk1_name"] = strTok("Recon,Sleight of Hand,Blind Eye,Extreme Conditioning,Scavenger", ",");
    level.cac["perk2"] = strTok("specialty_quickdraw,_specialty_blastshield,specialty_hardline,specialty_coldblooded,specialty_twoprimaries", ",");
    level.cac["perk2_name"] = strTok("Quickdraw,Blast Shield,Hardline,Assassin,Overkill", ",");
    level.cac["perk3"] = strTok("specialty_autospot,specialty_stalker,specialty_detectexplosive,specialty_bulletaccuracy,specialty_quieter", ",");
    level.cac["perk3_name"] = strTok("Marksman,Stalker,SitRep,Steady Aim,Dead Silence", ",");
    level.cac["deathstreak"] = strTok("specialty_null,specialty_juiced,specialty_revenge,specialty_finalstand,specialty_grenadepulldeath,specialty_c4death,specialty_stopping_power", ",");
    level.cac["deathstreak_name"] = strTok("None,Juiced,Revenge,Final Stand,Martyrdom,Dead Man's Hand,Hollow Points", ",");
    level.cac["equip"] = strTok("frag_grenade_mp,semtex_mp,throwingknife_mp,bouncingbetty_mp,claymore_mp,c4_mp", ",");
    level.cac["equip_name"] = strTok("Frag,Semtex,Throwing Knife,Bouncing Betty,Claymore,C4", ",");
    level.cac["tactical"] = strTok("flash_grenade_mp,concussion_grenade_mp,specialty_scrambler,emp_grenade_mp,smoke_grenade_mp,trophy_mp,specialty_tacticalinsertion,specialty_portable_radar", ",");
    level.cac["tactical_name"] = strTok("Flash Grenade,Concussion Grenade,Scrambler,EMP Grenade,Smoke Grenade,Trophy System,Tactical Insertion,Portable Radar", ",");
    level.cac["prof_ar"] = strTok("specialty_marksman,specialty_bulletpenetration,specialty_bling,specialty_sharp_focus,specialty_holdbreathwhileads,specialty_reducedsway", ",");
    level.cac["prof_ar_name"] = strTok("Kick,Impact,Attachments,Focus,Breath,Stability", ",");
    level.cac["prof_smg"] = strTok("specialty_marksman,specialty_longerrange,specialty_bling,specialty_sharp_focus,specialty_fastermelee,specialty_reducedsway", ",");
    level.cac["prof_smg_name"] = strTok("Kick,Range,Attachments,Focus,Melee,Stability", ",");
    level.cac["prof_lmg"] = strTok("specialty_marksman,specialty_bulletpenetration,specialty_bling,specialty_sharp_focus,specialty_lightweight,specialty_reducedsway", ",");
    level.cac["prof_lmg_name"] = strTok("Kick,Impact,Attachments,Focus,Speed,Stability", ",");
    level.cac["prof_sniper"] = strTok("specialty_marksman,specialty_bulletpenetration,specialty_bling,specialty_sharp_focus,specialty_lightweight,specialty_reducedsway", ",");
    level.cac["prof_sniper_name"] = strTok("Kick,Impact,Attachments,Focus,Speed,Stability", ",");
    level.cac["prof_shotgun"] = strTok("specialty_marksman,specialty_sharp_focus,specialty_bling,specialty_fastermelee,specialty_longerrange,specialty_moredamage", ",");
    level.cac["prof_shotgun_name"] = strTok("Kick,Focus,Attachments,Melee,Range,Damage", ",");
    level.cac["prof_shield"] = strTok("specialty_fastermelee,specialty_lightweight", ",");
    level.cac["prof_shield_name"] = strTok("Melee,Speed", ",");
    level.cac["wep_prof_type"] = [];
    foreach (w in level.cac["ar"]) level.cac["wep_prof_type"][w] = "ar";
    foreach (w in level.cac["smg"]) level.cac["wep_prof_type"][w] = "smg";
    foreach (w in level.cac["lmg"]) level.cac["wep_prof_type"][w] = "lmg";
    foreach (w in level.cac["sniper"]) level.cac["wep_prof_type"][w] = "sniper";
    foreach (w in level.cac["shotgun"]) level.cac["wep_prof_type"][w] = "shotgun";
    foreach (w in level.cac["shield"]) level.cac["wep_prof_type"][w] = "shield";
    level.cac_names = [];
    k = strTok("iw5_m4,iw5_m16,iw5_scar,iw5_cm901,iw5_type95,iw5_g36c,iw5_acr,iw5_mk14,iw5_ak47,iw5_fad,iw5_mp5,iw5_ump45,iw5_pp90m1,iw5_p90,iw5_m9,iw5_mp7,iw5_sa80,iw5_mg36,iw5_pecheneg,iw5_mk46,iw5_m60,iw5_barrett,iw5_l96a1,iw5_dragunov,iw5_as50,iw5_rsass,iw5_msr,iw5_usas12,iw5_ksg,iw5_spas12,iw5_aa12,iw5_striker,iw5_1887,riotshield,iw5_fmg9,iw5_mp9,iw5_skorpion,iw5_g18,iw5_usp45,iw5_p99", ",");
    v = strTok("M4A1,M16A4,SCAR-L,CM901,Type 95,G36C,ACR 6.8,MK14,AK-47,FAD,MP5,UMP45,PP90M1,P90,PM-9,MP7,L86 LSW,MG36,PKP Pecheneg,MK46,M60E4,Barrett .50cal,L118A,Dragunov,AS50,Rsass,MSR,USAS 12,KSG 12,SPAS-12,AA-12,Striker,Model 1887,Riot Shield,FMG9,MP9,Skorpion,G18,USP .45,P99", ",");
    for (i = 0; i < k.size; i++) level.cac_names[k[i]] = v[i];
    k = strTok("iw5_mp412,iw5_44magnum,iw5_fnfiveseven,iw5_deserteagle,iw5_smaw,javelin,stinger,xm25,rpg,specialty_paint,specialty_fastreload,specialty_blindeye,specialty_longersprint,specialty_scavenger,specialty_quickdraw,_specialty_blastshield,specialty_hardline,specialty_coldblooded,specialty_twoprimaries,specialty_autospot,specialty_stalker,specialty_detectexplosive,specialty_bulletaccuracy,specialty_quieter,specialty_juiced,specialty_revenge,specialty_finalstand,specialty_grenadepulldeath,specialty_c4death,specialty_stopping_power,frag_grenade_mp,semtex_mp,throwingknife_mp,bouncingbetty_mp,claymore_mp,c4_mp,flash_grenade_mp,concussion_grenade_mp,specialty_scrambler,emp_grenade_mp", ",");
    v = strTok("MP412,.44 Magnum,Five Seven,Desert Eagle,SMAW,Javelin,Stinger,XM25,RPG-7,Recon,Sleight of Hand,Blind Eye,Extreme Conditioning,Scavenger,Quickdraw,Blast Shield,Hardline,Assassin,Overkill,Marksman,Stalker,SitRep,Steady Aim,Dead Silence,Juiced,Revenge,Final Stand,Martyrdom,Dead Man's Hand,Hollow Points,Frag,Semtex,Throwing Knife,Bouncing Betty,Claymore,C4,Flash Grenade,Concussion Grenade,Scrambler,EMP Grenade", ",");
    for (i = 0; i < k.size; i++) level.cac_names[k[i]] = v[i];
    k = strTok("smoke_grenade_mp,trophy_mp,specialty_tacticalinsertion,specialty_portable_radar,specialty_null,specialty_marksman,specialty_bulletpenetration,specialty_bling,specialty_sharp_focus,specialty_holdbreathwhileads,specialty_reducedsway,specialty_longerrange,specialty_fastermelee,specialty_lightweight,specialty_moredamage,none,acog,reflex,silencer,silencer02,silencer03,grip,gl,gp25,m320,akimbo,thermal,shotgun,heartbeat,fmj,rof,xmags,lockair,boom,eotech,tactical,vzscope,hamrhybrid,hybrid,zoomscope", ",");
    v = strTok("Smoke Grenade,Trophy System,Tactical Insertion,Portable Radar,None,Kick,Impact,Attachments,Focus,Breath,Stability,Range,Melee,Speed,Damage,No Attachment,ACOG Scope,Red Dot Sight,Silencer,Silencer,Silencer,Grip,Grenade Launcher,Grenade Launcher,Grenade Launcher,Akimbo,Thermal,Shotgun,Heartbeat Sensor,FMJ,Rapid Fire,Extended Mags,Vehicle Lock-on,Sonic Boom,Holographic Sight,Tactical Knife,Variable Zoom Scope,HAMR scope,Hybrid Sight,Hybrid Scope", ",");
    for (i = 0; i < k.size; i++) level.cac_names[k[i]] = v[i];
    k = strTok("done,reflexsmg,reflexlmg,eotechsmg,eotechlmg,acogsmg,acoglmg,thermalsmg,thermallmg,uav,airdrop_assault,predator_missile,ims,airdrop_sentry_minigun,sentry,precision_airstrike,helicopter,littlebird_flock,littlebird_support,remote_mortar,airdrop_remote_tank,remote_tank,helicopter_flares,ac130,airdrop_juggernaut,osprey_gunner,uav_support,counter_uav,deployable_vest,airdrop_trap,sam_turret,remote_uav,triple_uav,remote_mg_turret,stealth_airstrike,emp,airdrop_juggernaut_recon,escort_airdrop,nuke,all_perks_bonus", ",");
    v = strTok("DONE,Red Dot Sight,Red Dot Sight,Holographic Sight,Holographic Sight,ACOG Scope,ACOG Scope,Thermal,Thermal,UAV,Care Package,Predator Missile,I.M.S.,Sentry Gun,Sentry Gun,Precision Airstrike,Attack Helicopter,Strafe Run,AH-6 Overwatch,Reaper,Assault Drone,Assault Drone,Pave Low,AC-130,Juggernaut,Osprey Gunner,UAV,Counter-UAV,Ballistic Vests,Airdrop Trap,SAM Turret,Recon Drone,Advanced UAV,Remote Sentry,Stealth Bomber,EMP,Juggernaut Recon,Escort Airdrop,M.O.A.B.,All Specialist Perks", ",");
    for (i = 0; i < k.size; i++) level.cac_names[k[i]] = v[i];
}
