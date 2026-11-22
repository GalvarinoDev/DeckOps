/*
    DeckOps Offline Menus (T4 / World at War MP, offline LAN server)
    Server-side GSC for the DeckOps offline server (Plutonium T4, -lan -dedicated), with the mod.ff menus
    (mods/mp_deckops_offline/mod.ff, built from WaW's own menus by build_waw_menus.py):
        - Create-a-Class is WaW's own, in game; classes are the offline profile's own stats (uploadstats)
        - Use Class in the editor: that class on the next spawn
        - Map / Mode and Bot Warfare menus: a row click sends one response, the server changes the setting and
          shows it through setClientDvar (a menu script stops after its first sent response)
        - OPTIONAL (DeckOps only, needs Bot Warfare): bots hold still while the Esc menu is open
*/

#include common_scripts\utility;
#include maps\mp\_utility;

init()
{
    level.dcac = dcacCatalog();
    restoreBotplay();
    level thread onPlayerConnect();
    level thread applyMatchOptions();
}

onPlayerConnect()
{
    for (;;)
    {
        level waittill("connected", player);
        // Bot Warfare doesn't set pers["isBot"] by "connected"
        if (player isBot())
        {
            player thread botGrenadeFix();
            continue;
        }
        player dlog("connected");
        player thread watchMenuResponses();
        player thread watchDeath();
        player thread watchSpawn();
    }
}

// A bot re-added mid-match (Bot Count 0, then up) can read special grenade 0, and WaW warns on screen.
// Hand it the molotov WaW falls back to anyway, before each spawn reads the class.
botGrenadeFix()
{
    self endon("disconnect");
    for (;;)
    {
        wait 0.05;
        for (i = 0; i < 5; i++)
        {
            g = self getStat(208 + i * 10);
            if (g != 101 && g != 102 && g != 103 && g != 105)
            {
                self setStat(208 + i * 10, 101);
                self.cac_initialized = undefined;
            }
        }
        self waittill("death");
    }
}

watchDeath()
{
    self endon("disconnect");
    for (;;)
    {
        self waittill("death");
        // WaW caches custom classes; rebuild from the stats the editor uploaded since
        self.cac_initialized = undefined;
    }
}

watchSpawn()
{
    self endon("disconnect");
    for (;;)
    {
        self waittill("spawned_player");
        wait 0.05;
        w = self getWeaponsList();
        line = "";
        for (i = 0; i < w.size; i++)
            line += " " + w[i];
        self dlog("spawned " + self.pers["class"] + ":" + line);
    }
}

// Test builds: +set dcac_debug 1 logs the menu flow to games_mp.log
dlog(msg)
{
    if (getDvarInt("dcac_debug"))
        logprint("DCAC;" + self.name + ";" + msg + "\n");
}

watchMenuResponses()
{
    self endon("disconnect");
    for (;;)
    {
        self waittill("menuresponse", menu, response);
        self dlog("menuresponse " + menu + " " + response);
        // OPTIONAL (DeckOps only, needs Bot Warfare): bots hold still while the Esc menu is open
        if (response == "dcac_pause")
            self menuPause();
        // Map / Mode and Bot Warfare menus (mod.ff): "m,<row>" / "b,<row>", one per click
        else if (getSubStr(response, 0, 2) == "m,")
            self matchMenu(getSubStr(response, 2));
        else if (getSubStr(response, 0, 2) == "b,")
            self botMenu(getSubStr(response, 2));
        // Use Class in WaW's editor (not a script menu, so WaW's own handler ignores it)
        else if (response.size == 9 && getSubStr(response, 0, 6) == "custom")
            self useEditedClass(int(getSubStr(response, 6, 7)) - 1);
    }
}

// Use Class in the editor: always the next spawn (WaW's own rule for a class change mid-life). The class is read
// from the uploaded stats at that spawn, so later edits to it count too.
useEditedClass(n)
{
    cls = "CLASS_CUSTOM" + (n + 1);
    self.pers["class"] = cls;
    self.class = cls;
    self.pers["weapon"] = undefined;
    self.cac_initialized = undefined;
    if (self.sessionstate == "playing")
        self iPrintLnBold(game["strings"]["change_class"]);
    self dlog("next spawn: custom" + (n + 1));
}

// --- Map / Mode

// Time and score limits are scr_<gametype>_* dvars the match logic keeps reading, so they change
// live. The gametype resets them on every map, so they are re-applied
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

// dcac_maps (set by the offline script) lists the installed maps; DLC maps may be missing
matchMaps()
{
    have = getDvar("dcac_maps");
    m = [];
    m["key"] = [];
    m["name"] = [];
    for (i = 0; i < level.dcac["map"].size; i++)
        if (have == "" || isSubStr("," + have + ",", "," + level.dcac["map"][i] + ","))
        {
            m["key"][m["key"].size] = level.dcac["map"][i];
            m["name"][m["name"].size] = level.dcac["map_name"][i];
        }
    return m;
}

// Map / Mode menu: a row click changes the pending choice, the menu shows it through dcac_m<row>.
// dcac_map<n> fill the map list (installed maps only)
matchMenu(r)
{
    modes = level.dcac["mode"];
    maps = matchMaps();
    if (!isDefined(self.mm_mode))
    {
        self.mm_mode = indexOf(modes, level.gameType);
        self.mm_map = indexOf(maps["key"], getDvar("mapname"));
        self.mm_time = getDvar("dcac_opt_timelimit");
        if (self.mm_time == "") self.mm_time = "" + getDvarInt("scr_" + level.gameType + "_timelimit");
        self.mm_score = getDvar("dcac_opt_score");
        if (self.mm_score == "") self.mm_score = "1";
    }
    if (r == "0")
        self.mm_mode = (self.mm_mode + 1) % modes.size;
    else if (r == "2")
        self.mm_time = nextOf(strTok("0,5,10,15,20,30", ","), self.mm_time);
    else if (r == "3")
        self.mm_score = nextOf(strTok("1,2,0,0.5", ","), self.mm_score);
    else if (r == "4")
    {
        self closeMenu();
        self closeInGameMenu();
        self thread startMatch();
        return;
    }
    else if (getSubStr(r, 0, 4) == "map,")
        self.mm_map = int(getSubStr(r, 4));
    else if (r == "refresh")
        for (i = 0; i < 24; i++)
        {
            if (i < maps["name"].size) self setClientDvar("dcac_map" + i, maps["name"][i]);
            else self setClientDvar("dcac_map" + i, "");
        }
    self setClientDvar("dcac_m0", "Game Type: " + level.dcac["mode_name"][self.mm_mode]);
    self setClientDvar("dcac_m1", "Map: " + maps["name"][self.mm_map]);
    self setClientDvar("dcac_mpic", "loadscreen_" + maps["key"][self.mm_map] + "_ig");
    self setClientDvar("dcac_mt", maps["name"][self.mm_map]);
    self setClientDvar("dcac_mu", level.dcac["mode_name"][self.mm_mode]);
    if (self.mm_time == "0") self setClientDvar("dcac_m2", "Time Limit: Unlimited");
    else self setClientDvar("dcac_m2", "Time Limit: " + self.mm_time + " min");
    self setClientDvar("dcac_m3", "Score Limit: " + scoreName(self.mm_score));
    self setClientDvar("dcac_m4", "Start Match");
}

// The value after cur in vals (wraps around, and is the first one when cur isn't listed)
nextOf(vals, cur)
{
    for (i = 0; i < vals.size; i++)
        if (vals[i] == cur)
            return vals[(i + 1) % vals.size];
    return vals[0];
}

indexOf(list, value)
{
    for (i = 0; i < list.size; i++)
        if (list[i] == value)
            return i;
    return 0;
}

scoreName(mult)
{
    if (mult == "0") return "Unlimited";
    if (mult == "0.5") return "Half";
    if (mult == "2") return "Double";
    return "Default";
}

startMatch()
{
    self endon("disconnect");

    maps = matchMaps();
    gt = level.dcac["mode"][self.mm_mode];
    setDvar("dcac_opt_timelimit", self.mm_time);
    setDvar("dcac_opt_score", self.mm_score);
    sameMatch = gt == level.gameType && maps["key"][self.mm_map] == getDvar("mapname");

    if (sameMatch)
    {
        level thread applyMatchOptions();
        self iPrintLnBold("^2Match settings applied");
        self.mm_mode = undefined;
        return;
    }

    rot = "gametype " + gt + " map " + maps["key"][self.mm_map];
    name = maps["name"][self.mm_map] + " - " + level.dcac["mode_name"][self.mm_mode];
    self.mm_mode = undefined;
    setDvar("sv_maprotation", rot);
    setDvar("sv_maprotationcurrent", rot);
    iPrintLnBold("^2Loading ^7" + name);
    wait 2;
    exitLevel(false);
}

// --- Bot Warfare (reads these dvars live)

// Bot Warfare menu: a row click cycles that setting, the menu shows it through dcac_b<row>
botMenu(r)
{
    if (r == "0")
    {
        // bots_manage_fill counts the player too; sv_maxclients 13 = 12 bots + the player
        bots = getDvarInt("bots_manage_fill") - 1;
        if (bots < 0) bots = 0;
        bots = int(nextOf(strTok("0,2,4,6,8,10,12", ","), "" + bots));
        if (bots > 0) bots++;
        setDvar("bots_manage_fill", "" + bots);
    }
    else if (r == "1")
        setDvar("bots_skill", nextOf(strTok("0,1,3,5,7", ","), "" + getDvarInt("bots_skill")));
    else if (r == "2")
    {
        if (getDvar("bots_team") == "autoassign" || getDvar("bots_team") == "")
        {
            if (self.team == "axis") setDvar("bots_team", "allies");
            else setDvar("bots_team", "axis");
            setDvar("bots_team_force", "1");
        }
        else
        {
            setDvar("bots_team", "autoassign");
            setDvar("bots_team_force", "0");
        }
    }
    else if (r == "3") botToggle("bots_play_obj");
    else if (r == "4") botToggle("bots_play_camp");
    else if (r == "5") botToggle("bots_play_killstreak");
    else if (r == "6") botToggle("bots_play_jumpdrop");
    else if (r == "7")
    {
        op = getDvarInt("bots_loadout_allow_op");
        setDvar("bots_loadout_allow_op", "" + !op);
        setDvar("bots_loadout_reasonable", "" + op);
    }
    else if (r == "8")
    {
        c = getDvarFloat("bots_main_chat");
        if (c <= 0) setDvar("bots_main_chat", "1");
        else if (c < 2) setDvar("bots_main_chat", "3");
        else setDvar("bots_main_chat", "0");
    }
    items = self botLabels();
    for (i = 0; i < items.size; i++)
        self setClientDvar("dcac_b" + i, items[i]);
}

botLabels()
{
    items = [];
    bots = getDvarInt("bots_manage_fill") - 1;
    if (bots < 0) bots = 0;
    items[0] = "Bot Count: " + bots;
    items[1] = "Difficulty: " + botSkillName(getDvarInt("bots_skill"));
    if (getDvar("bots_team") == "autoassign" || getDvar("bots_team") == "") items[2] = "Bot Team: Balanced";
    else items[2] = "Bot Team: All Enemies";
    items[3] = "Play Objective: " + onOff(botSetting("bots_play_obj"));
    items[4] = "Camping: " + onOff(botSetting("bots_play_camp"));
    items[5] = "Killstreaks: " + onOff(botSetting("bots_play_killstreak"));
    items[6] = "Jump & Dropshot: " + onOff(botSetting("bots_play_jumpdrop"));
    if (getDvarInt("bots_loadout_allow_op")) items[7] = "Bot Classes: Anything Goes";
    else items[7] = "Bot Classes: Sensible";
    c = getDvarFloat("bots_main_chat");
    if (c <= 0) items[8] = "Bot Chat: Off";
    else if (c < 2) items[8] = "Bot Chat: Normal";
    else items[8] = "Bot Chat: Chatty";
    return items;
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
    {
        level.dcac_botplay[dvar] = v;
        saveBotplay();
    }
    else
        setDvar(dvar, v);
}

botSkillName(n)
{
    if (n == 0) return "Mixed";
    if (n <= 2) return "Easy";
    if (n <= 4) return "Normal";
    if (n <= 6) return "Hard";
    return "Veteran";
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
    saveBotplay();
}

// bots_play_* outlive the level but level.dcac_botplay doesn't: a map change or an S&D round
// (map_restart) while paused would leave the bots frozen, so the values to restore go in a dvar too
saveBotplay()
{
    s = "";
    keys = getArrayKeys(level.dcac_botplay);
    for (i = 0; i < keys.size; i++)
        s += keys[i] + "=" + level.dcac_botplay[keys[i]] + ",";
    setDvar("dcac_botplay", s);
}

restoreBotplay()
{
    s = getDvar("dcac_botplay");
    if (s == "")
        return;
    pairs = strTok(s, ",");
    for (i = 0; i < pairs.size; i++)
    {
        kv = strTok(pairs[i], "=");
        if (kv.size > 1) setDvar(kv[0], kv[1]);
        else setDvar(kv[0], "");
    }
    setDvar("dcac_botplay", "");
}

// OPTIONAL: the Esc menu sends dcac_pause when it opens (Create-a-Class is reached through it). Menus can't send
// a close (a response in onClose ends Use Class / Back), so the bots resume once the view moves again or the
// player stops playing, which only happens with every menu closed.
menuPause()
{
    if (isDefined(self.dcac_paused))
        return;
    self.dcac_paused = true;
    self botsPause();
    level thread menuPauseWatch(self);
}

// On level, so a disconnect still resumes the bots
menuPauseWatch(p)
{
    angles = p getPlayerAngles();
    for (;;)
    {
        wait 0.2;
        if (!isDefined(p) || p.sessionstate != "playing" || p getPlayerAngles() != angles)
            break;
    }
    if (isDefined(p))
        p.dcac_paused = undefined;
    botsResume();
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
    setDvar("dcac_botplay", "");
}

// Maps and modes in WaW's order, names from its own strings (gen_catalog.py)
dcacCatalog()
{
    c = [];
    c["map"] = strTok("mp_airfield,mp_asylum,mp_castle,mp_shrine,mp_courtyard,mp_dome,mp_downfall,mp_hangar,mp_makin,mp_outskirts,mp_roundhouse,mp_seelow,mp_suburban,mp_kneedeep,mp_makin_day,mp_nachtfeuer,mp_subway,mp_kwai,mp_stalingrad,mp_docks,mp_drum,mp_bgate,mp_vodka", ",");
    c["map_name"] = strTok("Airfield,Asylum,Castle,Cliffside,Courtyard,Dome,Downfall,Hangar,Makin,Outskirts,Roundhouse,Seelow,Upheaval,Knee Deep,Makin Day,Nightfire,Station,Banzai,Corrosion,Sub Pens,Battery,Breach,Revolution", ",");
    c["mode"] = strTok("dm,dom,sd,sab,tdm,koth,twar,ctf", ",");
    c["mode_name"] = strTok("Free-for-all,Domination,Search and Destroy,Sabotage,Team Deathmatch,Headquarters,War,Capture the Flag", ",");
    return c;
}
