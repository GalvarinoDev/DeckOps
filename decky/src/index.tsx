import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  staticClasses,
  definePlugin,
} from "@decky/ui";
import {
  callable,
  toaster,
} from "@decky/api";
import { useState, useEffect } from "react";
import { FaTv } from "react-icons/fa";

// ── Python backend calls ────────────────────────────────────────────────────

const isInstalled = callable<[], {
  installed: boolean;
}>("is_installed");

const downloadDeckops = callable<[], {
  success: boolean;
  message: string;
}>("download_deckops");

const getStatus = callable<[], {
  mode: string;
  deck_model: string;
  docked_resolution: string | null;
  external_connected: boolean;
  external_resolution: string | null;
  external_aspect_ratio: string | null;
  matched_resolution: string | null;
  needs_testing: boolean;
  handheld_refresh: string;
  handheld_resolution: string;
}>("get_status");

const setHandheld = callable<[], {
  mode: string;
  resolution: string;
  refresh_rate: string;
  patched: number;
  failed: number;
  total: number;
}>("set_handheld");

const setDocked = callable<[resolution: string | null], {
  mode: string;
  resolution: string;
  refresh_rate: string;
  patched: number;
  failed: number;
  total: number;
}>("set_docked");

const detectDisplay = callable<[], {
  connected: boolean;
  resolution: string | null;
  aspect_ratio: string | null;
  matched_res: string | null;
  needs_testing: boolean;
}>("detect_display");

const enableFileEditing = callable<[], {
  unlocked: number;
  failed: number;
  total: number;
}>("enable_file_editing");

// ── Main UI Component ───────────────────────────────────────────────────────

function Content() {
  const [installed, setInstalled] = useState<boolean | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [isDocked, setIsDocked] = useState(false);
  const [currentRes, setCurrentRes] = useState("1280x800");
  const [refreshRate, setRefreshRate] = useState("60 Hz");
  const [handheldRes, setHandheldRes] = useState("1280x800");
  const [handheldRefresh, setHandheldRefresh] = useState("60 Hz");
  const [externalConnected, setExternalConnected] = useState(false);
  const [externalRes, setExternalRes] = useState<string | null>(null);
  const [matchedRes, setMatchedRes] = useState<string | null>(null);
  const [needsTesting, setNeedsTesting] = useState(false);
  const [externalRatio, setExternalRatio] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [configCount, setConfigCount] = useState(0);
  const [editingEnabled, setEditingEnabled] = useState(false);

  // Check install status on mount
  useEffect(() => {
    checkInstalled();
  }, []);

  const checkInstalled = async () => {
    try {
      const result = await isInstalled();
      setInstalled(result.installed);
      if (result.installed) {
        loadStatus();
      }
    } catch (e) {
      console.error("DeckOps: Failed to check install status", e);
      setInstalled(false);
    }
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const result = await downloadDeckops();
      if (result.success) {
        setInstalled(true);
        toaster.toast({
          title: "DeckOps",
          body: result.message,
        });
      } else {
        toaster.toast({
          title: "DeckOps",
          body: result.message,
        });
      }
    } catch (e) {
      console.error("DeckOps: Download failed", e);
      toaster.toast({
        title: "DeckOps",
        body: "Download failed. Check your internet connection.",
      });
    }
    setDownloading(false);
  };

  const loadStatus = async () => {
    try {
      const status = await getStatus();
      setIsDocked(status.mode === "docked");
      setHandheldRes(status.handheld_resolution);
      setHandheldRefresh(status.handheld_refresh);
      setRefreshRate(
        status.mode === "docked"
          ? "auto"
          : status.handheld_refresh
      );

      if (status.mode === "docked" && status.docked_resolution) {
        setCurrentRes(status.docked_resolution);
      } else {
        setCurrentRes(status.handheld_resolution);
      }

      setExternalConnected(status.external_connected);
      setExternalRes(status.external_resolution);
      setMatchedRes(status.matched_resolution);
      setNeedsTesting(status.needs_testing);
      setExternalRatio(status.external_aspect_ratio);
    } catch (e) {
      console.error("DeckOps: Failed to get status", e);
    }
  };

  const handleToggle = async (docked: boolean) => {
    setLoading(true);
    try {
      let result;
      if (docked) {
        result = await setDocked(null);
      } else {
        result = await setHandheld();
      }

      setIsDocked(docked);
      setCurrentRes(result.resolution);
      setRefreshRate(result.refresh_rate);
      setConfigCount(result.patched);
      setEditingEnabled(false);

      toaster.toast({
        title: "DeckOps Display",
        body: docked
          ? `Docked: ${result.resolution} (${result.patched} configs updated)`
          : `Handheld: ${result.resolution} (${result.patched} configs updated)`,
      });
    } catch (e) {
      console.error("DeckOps: Failed to toggle mode", e);
      toaster.toast({
        title: "DeckOps Display",
        body: "Failed to switch display mode",
      });
    }
    setLoading(false);
  };

  const handleRefreshDisplay = async () => {
    try {
      const info = await detectDisplay();
      setExternalConnected(info.connected);
      setExternalRes(info.resolution);
      setMatchedRes(info.matched_res);
      setNeedsTesting(info.needs_testing);
      setExternalRatio(info.aspect_ratio);
    } catch (e) {
      console.error("DeckOps: Failed to detect display", e);
    }
  };

  const handleEnableEditing = async () => {
    try {
      const result = await enableFileEditing();
      setEditingEnabled(true);
      toaster.toast({
        title: "DeckOps Display",
        body: `Game configs unlocked for editing (${result.unlocked} files). Will re-lock on next mode switch.`,
      });
    } catch (e) {
      console.error("DeckOps: Failed to enable file editing", e);
    }
  };

  // ── Loading state (checking install) ──────────────────────────────────
  if (installed === null) {
    return (
      <PanelSection title="DeckOps">
        <PanelSectionRow>
          <div style={{ fontSize: "12px", color: "#b8bcbf", padding: "0 16px" }}>
            Checking installation...
          </div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  // ── Not installed — show download UI ──────────────────────────────────
  if (!installed) {
    return (
      <PanelSection title="DeckOps">
        <PanelSectionRow>
          <div style={{ fontSize: "12px", color: "#b8bcbf", padding: "0 16px" }}>
            DeckOps is not installed. Download it to set up Call of Duty on your device.
          </div>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={handleDownload}
            disabled={downloading}
          >
            {downloading ? "Downloading DeckOps..." : "Download DeckOps"}
          </ButtonItem>
        </PanelSectionRow>

        {downloading && (
          <PanelSectionRow>
            <div style={{ fontSize: "11px", color: "#7c7e80", padding: "0 16px" }}>
              This may take a minute. Please don't close this menu.
            </div>
          </PanelSectionRow>
        )}
      </PanelSection>
    );
  }

  // ── Installed — show display toggle UI ────────────────────────────────
  return (
    <PanelSection title="Display Mode">
      <PanelSectionRow>
        <ToggleField
          label="Docked Mode"
          description={
            isDocked
              ? `${currentRes} @ ${refreshRate}`
              : `Handheld: ${handheldRes} @ ${handheldRefresh}`
          }
          checked={isDocked}
          disabled={loading}
          onChange={handleToggle}
        />
      </PanelSectionRow>

      {externalConnected && !needsTesting && (
        <PanelSectionRow>
          <div style={{ fontSize: "12px", color: "#b8bcbf", padding: "0 16px" }}>
            External display: {externalRes}
            {matchedRes && matchedRes !== externalRes && (
              <span> → using {matchedRes}</span>
            )}
          </div>
        </PanelSectionRow>
      )}

      {externalConnected && needsTesting && (
        <PanelSectionRow>
          <div style={{ fontSize: "12px", color: "#dcb458", padding: "0 16px" }}>
            {externalRatio} display detected ({externalRes}). Using {matchedRes} — this aspect ratio is experimental and may not work with all games.
          </div>
        </PanelSectionRow>
      )}

      {!externalConnected && isDocked && (
        <PanelSectionRow>
          <div style={{ fontSize: "12px", color: "#dcb458", padding: "0 16px" }}>
            No external display detected — using last known resolution
          </div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={handleEnableEditing}
          disabled={loading || editingEnabled}
        >
          {editingEnabled ? "Game Config Editing Enabled" : "Allow Game Config Editing"}
        </ButtonItem>
      </PanelSectionRow>

      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={handleRefreshDisplay}
          disabled={loading}
        >
          Refresh Display Detection
        </ButtonItem>
      </PanelSectionRow>

      {configCount > 0 && (
        <PanelSectionRow>
          <div style={{ fontSize: "11px", color: "#7c7e80", padding: "0 16px" }}>
            Last update: {configCount} config{configCount !== 1 ? "s" : ""} patched
          </div>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// ── Plugin Registration ─────────────────────────────────────────────────────

export default definePlugin(() => {
  console.log("DeckOps display plugin loaded");

  return {
    name: "DeckOps",
    titleView: <div className={staticClasses.Title}>DeckOps</div>,
    content: <Content />,
    icon: <FaTv />,
    onDismount() {
      console.log("DeckOps display plugin unloaded");
    },
  };
});
