# DeckOps

<p align="center">
  <img src="assets/images/DeckOps-banner.png" alt="DeckOps - CombatOnDeck" width="460"/>
</p>

<p align="center">
  Bringing the Golden Age of FPS to your Steam Deck, no terminal required.
</p>

---

DeckOps automates the installation of iw4x, CoD4x, IW3SP-MOD, and Plutonium on Steam Deck. Pick your games, hit install, and launch them straight from Steam like any other game.

---

## 💾 Installation & Uninstall

1. Press the Steam button -> **Power** -> **Switch to Desktop**

2. Open a browser and navigate to this GitHub page

3. Download the **[DeckOps file](https://github.com/GalvarinoDev/DeckOps/releases/download/v1/DeckOps.desktop)**

4. Right-click the file -> **Properties** -> **Permissions** -> tick **"Is executable"** -> OK

5. Double-click it
   - **First time:** DeckOps installs automatically
   - **Already installed:** A menu appears - choose to Launch, Reinstall, or Uninstall

> Keep the DeckOps file on your Deck. Double-clicking it is how you launch, reinstall, or uninstall DeckOps in the future.

> Your Steam games are never touched. Only the files DeckOps created are removed during uninstall.

---

## 📋 Requirements

- Each supported game must be **installed through Steam and launched at least once** in the correct modes before running DeckOps - see the table below. DeckOps will show which games aren't ready and prevent you from selecting them.
- Plutonium games require a free account at [plutonium.pw](https://plutonium.pw)

---

## ⚠️ Before You Install

**Each game must be launched through Steam in the correct modes before running DeckOps.** This creates the Proton prefix and starts shader cache downloads. Skipping this step is the most common cause of install failures.

| Game | Launch these modes in Steam first |
|---|---|
| Call of Duty 4 | Multiplayer **and** Singleplayer |
| Modern Warfare 2 | Multiplayer |
| Modern Warfare 3 | Multiplayer |
| World at War | Campaign **and** Multiplayer |
| Black Ops | Campaign **and** Multiplayer (these are separate Steam library entries - launch both) |
| Black Ops II | Multiplayer **and** Zombies |

---

## ⚠️ After Installation

**Do not open Steam in Desktop Mode. Switch to Game Mode and launch every modded game at least once.** Steam Cloud will overwrite your DeckOps setup if you open Steam while in Desktop Mode, which will require you to uninstall DeckOps and reinstall. Once every modded game has been launched in Game Mode at least once, it is safe to use Steam in Desktop Mode.

If Steam asks about cloud saves, choose **Keep Local**. If a game asks for Safe Mode, choose **No**.

**When launching Modern Warfare 1 or World at War for the first time after DeckOps install, Steam will ask which mode you want to launch.** Select Singleplayer or Campaign and set it as your default. Multiplayer for these games launches via the DeckOps shortcuts in your library instead.

**Black Ops II config files are encrypted and cannot be written by DeckOps.** Set your resolution and display settings in-game after launching for the first time.

---

## 🎮 Supported Games

| Game | Client | Deck Model | Modes | Controller | Aim Assist | Gyro |
|---|---|---|---|---|---|---|
| Modern Warfare 1 - Campaign | IW3SP-MOD | LCD + OLED | SP | ✅ | ✅ | ✅ |
| Modern Warfare 1 - Multiplayer | CoD4x | LCD + OLED | MP | ✅ | ❌ | ✅ |
| Modern Warfare 2 - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Modern Warfare 2 - Multiplayer | iw4x | LCD + OLED | MP | ✅ | ✅ | ✅ |
| Modern Warfare 3 - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Modern Warfare 3 - Multiplayer | Plutonium | OLED only | MP | ✅ | ✅ | ✅ |
| World at War - Campaign & Multiplayer & Zombies | Plutonium | OLED only | SP / MP / ZM | ✅ | ✅ | ✅ |
| Black Ops - Campaign & Multiplayer & Zombies | Plutonium | OLED only | SP / MP / ZM | ✅ | ✅ | ✅ |
| Black Ops II - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Black Ops II - Multiplayer & Zombies | Plutonium | OLED only | MP / ZM | ✅ | ✅ | ✅ |

> Gyro aiming works on all titles via Steam Input. Choose **Hold** (R5 held) or **Toggle** (R5 press) during setup. Change anytime in **Settings -> Re-apply Controller Profiles**.

> **Steam Deck LCD:** Plutonium online servers require OLED. For offline Campaign and Zombies on LCD, see [PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher).

---

## 🔧 Troubleshooting

**Modern Warfare 1 Multiplayer won't launch or crashes on first run?**
This is normal - it needs to be launched three times through Steam to finish setup. Launch it once, let it close, launch it again, let it close, then on the third launch it will work.

**Game is showing the wrong resolution, display settings, or shortcuts not using GE-Proton?**
Display configs are only applied during initial setup. To fix resolution or display issues, go to **Settings -> Repair Shortcuts** to re-apply GE-Proton and controller configs, then reinstall DeckOps to re-apply display settings.

**Controller profiles not working?**
Go to **Settings -> Re-apply Controller Profiles** to reinstall controller templates.

**Plutonium login expired or not working?**
Go to **Settings -> Reset Credentials** to clear your saved login, then launch any Plutonium game to log in again. After logging in, use **Settings -> Sync to All Prefixes** to copy credentials to all game prefixes.

**Game asks for Safe Mode or to override config?**
Choose **No** - DeckOps has already configured optimal settings.

**Cloud save out of sync?**
Choose **Keep Local** to preserve DeckOps settings.

**Something went wrong during install?**
Check the install log at the bottom of the install screen. It shows exactly which configs were applied, skipped, or failed. If reporting a bug, include the full log output.

---

## Credits

**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - Original inspiration for DeckOps.

---

**DeckOps is an installer. The projects below are what actually make it work.**

**[Plutonium](https://plutonium.pw)** - MW3, World at War, Black Ops, Black Ops II. 💰 [Donate](https://forum.plutonium.pw/donate)

**[iw4x](https://iw4x.io)** - Modern Warfare 2. [GitHub](https://github.com/iw4x)

**[CoD4x](https://cod4x.ovh)** - Call of Duty 4. [GitHub](https://github.com/callofduty4x)

**[IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod)** - CoD4 Campaign mod by JerryALT.

Steam artwork from [SteamGridDB](https://www.steamgriddb.com) - thanks to [Moohoo](https://www.steamgriddb.com/profile/76561198009314736), [jarvis](https://www.steamgriddb.com/profile/76561198103947979), [Ramjez](https://www.steamgriddb.com/profile/76561198122547176), [Over](https://www.steamgriddb.com/profile/76561198049670875), [Uravity-PRO](https://www.steamgriddb.com/profile/76561198167607660), and [Maxine](https://www.steamgriddb.com/profile/76561198130550992).

**[Claude](https://claude.ai)** by Anthropic - assisted in development.

---

> DeckOps is not affiliated with Activision, Infinity Ward, Treyarch, or Valve. All trademarks belong to their respective owners. A legitimate Steam copy of each game is required. DeckOps does not provide or distribute game files.

## License

[MIT License](LICENSE)
