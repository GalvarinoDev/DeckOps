# DeckOps

<p align="center">
  <img src="assets/images/DeckOps-banner.png" alt="DeckOps - CombatOnDeck" width="460"/>
</p>

<p align="center">
  Bringing the golden era of FPS to your Steam Deck, no terminal required.
</p>

---

DeckOps automates the installation of iw4x, CoD4x, IW3SP-MOD, and Plutonium on Steam Deck. Pick your games, hit install, and launch them straight from Steam like any other game.

---

## 💾 Installation & Uninstall

1. Press the Steam button → **Power** → **Switch to Desktop**
   - Use the right trackpad as a mouse and press **Steam + X** to open the on-screen keyboard if needed

2. Navigate to this GitHub page in a browser

3. Download the **[DeckOps file](https://github.com/GalvarinoDev/DeckOps/releases/download/v1/DeckOps.desktop.download)**

4. Right-click the file → **Properties** → **Permissions** → tick **"Is executable"** → OK

5. Double-click it
   - **First time:** DeckOps installs automatically
   - **Already installed:** A menu appears - choose to Launch, Reinstall, or Uninstall

> Your Steam games are never touched. Only the files DeckOps created are removed during uninstall.

---

## Requirements

- Steam Deck running SteamOS
- Each game installed through Steam and launched at least once before running DeckOps in exactly these modes:
  - **CoD4** - Multiplayer and Singleplayer
  - **MW2** - Multiplayer
  - **MW3** - Multiplayer
  - **World at War** - Campaign/Zombies and Multiplayer
  - **Black Ops** - Campaign/Zombies and Multiplayer
  - **Black Ops II** - Zombies and Multiplayer
- Plutonium games require a free account at [plutonium.pw](https://plutonium.pw)

> Skipping the first-launch step is the #1 cause of install failures. It creates the Proton prefix and starts shader cache downloads.

---

## How It Works

DeckOps is a setup and management tool, not a launcher. Once your games are set up, launch them directly from Steam's Game Mode like any other game.

Open DeckOps whenever you want to update a client, reinstall after a Steam game update, add a newly purchased game, or re-apply controller templates.

---

## 🎮 Supported Games

DeckOps installs four controller templates into Steam during setup - two gyro layouts (Hold or Toggle) and two additional layouts for games that need them. Steam Input is enabled automatically for every supported game.

After install, DeckOps walks you through which template to apply for each game. You can revisit this guide at any time from **DeckOps → Settings → Setup Guide**.

You can re-apply controller templates at any time from **DeckOps → Settings → Re-apply Templates**.

| Game | Client | Deck Model | Modes | Controller | Aim Assist | Gyro |
|---|---|---|---|---|---|---|
| Modern Warfare 1 - Campaign | IW3SP-MOD | LCD + OLED | SP | ✅ | ✅ | ✅ |
| Modern Warfare 1 - Multiplayer | CoD4x | LCD + OLED | MP | ✅ | ❌ | ✅ |
| Modern Warfare 2 - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Modern Warfare 2 - Multiplayer | iw4x | LCD + OLED | MP | ✅ | ✅ | ✅ |
| Modern Warfare 3 - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Modern Warfare 3 - Multiplayer | Plutonium | OLED only | MP | ✅ | ✅ | ✅ |
| World at War | Plutonium | OLED only | SP / MP / ZM | ✅ | ✅ | ✅ |
| Black Ops | Plutonium | OLED only | SP / MP / ZM | ✅ | ✅ | ✅ |
| Black Ops II - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Black Ops II - Multiplayer & Zombies | Plutonium | OLED only | MP / ZM | ✅ | ✅ | ✅ |

> A legitimate Steam copy of each game is required. DeckOps does not provide or distribute game files.

> Gyro is implemented via Steam Input and works on all titles regardless of native client support.

### 📟 Steam Deck LCD - Plutonium Offline Play

Plutonium's dedicated server features are currently only stable on the Steam Deck OLED. If you have an LCD model and want to experience what Plutonium has to offer offline - including the improved fixed campaigns for World at War and Black Ops, or Zombies without needing an internet connection - check out **[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** by framilano. It's a lightweight launcher that gets Plutonium running outside of Steam, making it a great fit for LCD users who want the best single player and Zombies experience these titles have to offer.

---

## Credits

DeckOps is an installer. The projects below are what actually make it work.

**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - framilano's project was the original inspiration for DeckOps. If you're on a Steam Deck LCD and want to play Plutonium's improved campaigns or Zombies offline, his launcher is the way to go.

**[Plutonium](https://plutonium.pw)** - MW3, World at War, Black Ops, Black Ops II  
Community client with dedicated servers, mod support, and anti-cheat.  
💰 [Donate](https://forum.plutonium.pw/donate)

**[iw4x](https://iw4x.io)** - Modern Warfare 2  
Community MW2 client with dedicated servers and mod support.  
[GitHub](https://github.com/iw4x)

**[CoD4x](https://cod4x.ovh)** - Call of Duty 4  
Community CoD4 client.  
[GitHub](https://github.com/callofduty4x)

**[IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod)** - Call of Duty 4 Campaign  
Campaign mod by **JerryALT** bringing gamepad support, aim assist, achievements, and Workshop mod support to CoD4's campaign.  
[Gitea](https://gitea.com/JerryALT/iw3sp_mod)

**[Claude](https://claude.ai)** by Anthropic - assisted in the development of DeckOps.


---

DeckOps takes no money and has no affiliation with any of the above projects. All client software is downloaded directly from each project's official sources at install time.

---

## License

[MIT License](LICENSE)

---

## Disclaimer

DeckOps is not affiliated with Activision, Infinity Ward, Treyarch, or Valve. All trademarks belong to their respective owners. Use of community clients may violate the terms of service of the original games. Use at your own discretion.
