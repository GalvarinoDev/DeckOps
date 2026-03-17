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

2. Download the **[DeckOps file](https://github.com/GalvarinoDev/DeckOps/releases/download/v1/DeckOps.desktop.download)** from this page

3. Right-click the file -> **Properties** -> **Permissions** -> tick **"Is executable"** -> OK

4. Double-click it
   - **First time:** DeckOps installs automatically
   - **Already installed:** A menu appears - choose to Launch, Reinstall, or Uninstall

> Keep the DeckOps file on your Deck. Double-clicking it is how you launch, reinstall, or uninstall DeckOps in the future.

> Your Steam games are never touched. Only the files DeckOps created are removed during uninstall.

---

## 📋 Requirements

- Steam Deck running SteamOS
- GE-Proton will be automatically downloaded and installed by DeckOps if not already present
- Plutonium games require a free account at [plutonium.pw](https://plutonium.pw)
- Each supported game must be **installed through Steam and launched at least once** before running DeckOps - see the table below for which modes need to be launched

> DeckOps will show which games haven't been launched yet and prevent you from selecting them until they're ready.

> **GE-Proton:** If you already have GE-Proton installed (e.g. via ProtonUp-Qt), DeckOps will use it. If a newer version is available it will be downloaded automatically.

---

## ⚠️ Before You Install

**Each game must be launched through Steam in the correct modes before running DeckOps.** This creates the Proton prefix and starts shader cache downloads. Skipping this step is the most common cause of install failures.

| Game | Launch these modes in Steam first |
|---|---|
| Call of Duty 4 | Multiplayer **and** Singleplayer |
| Modern Warfare 2 | Multiplayer |
| Modern Warfare 3 | Multiplayer |
| World at War | Campaign **and** Multiplayer |
| Black Ops | Campaign **and** Multiplayer |
| Black Ops II | Multiplayer **and** Zombies |

> CoD4 Singleplayer and Multiplayer share the same Steam appid - both modes must be launched so DeckOps can set up IW3SP-MOD (SP) and CoD4x (MP) correctly.

> MW2 and MW3 Campaign are launched natively through Steam - no extra steps needed for those.

---

## ⚠️ After Installation

**Launch Steam in Desktop Mode before switching to Game Mode.** This lets Steam reload the config changes DeckOps made. Then switch to Game Mode and play normally.

**If Steam asks about cloud saves, choose Keep Local.** DeckOps writes display and controller configs locally - choosing Upload or letting Steam overwrite will undo them.

**When launching Modern Warfare 1 or World at War for the first time after DeckOps install, Steam will ask which mode you want to launch.** Select Singleplayer or Campaign and set it as your default. Multiplayer for these games launches via the DeckOps shortcuts in your library instead.

**Black Ops II graphics settings must be set manually.** BO2 config files are encrypted and cannot be written by DeckOps. Set your resolution and display settings in-game after launching for the first time.

> DeckOps sets GE-Proton as the compatibility tool for all supported games. Other games in your library are not affected.

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

> Gyro is implemented via Steam Input and works on all titles regardless of native client support. During setup you'll choose between **Hold** (gyro active while R5 is held) or **Toggle** (R5 press turns gyro on/off). You can change this anytime in **Settings → Re-apply Controller Profiles**.

> **Steam Deck LCD:** Plutonium online servers require OLED. For offline Campaign and Zombies on LCD, see [PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher).

---

## 🔧 Troubleshooting

**Modern Warfare 1 Multiplayer won't launch or crashes on first run?**
This is normal - it needs to be launched three times through Steam to finish setup. Launch it once, let it close, launch it again, let it close, then on the third launch it will work.

**Game is showing the wrong resolution or display settings?**
Go to **Settings -> Repair Shortcuts** - this will also re-apply the optimal display config for each game.

**Shortcuts not using GE-Proton?**
Go to **Settings -> Repair Shortcuts** to re-apply GE-Proton and controller configs.

**Controller profiles not working?**
Go to **Settings -> Re-apply Controller Profiles** to reinstall controller templates.

**Game asks for Safe Mode or to override config?**
Choose **No** - DeckOps has already configured optimal settings.

**Cloud save out of sync?**
Choose **Keep Local** to preserve DeckOps settings.

---

## Credits

DeckOps is an installer. The projects below are what actually make it work.

**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - Original inspiration for DeckOps.

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
