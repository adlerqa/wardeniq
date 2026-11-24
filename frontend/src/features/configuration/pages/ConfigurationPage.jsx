import LlmSettingsCard from "../components/LlmSettingsCard.jsx";
import EmbeddingSettingsCard from "../components/EmbeddingSettingsCard.jsx";
import AtlassianSettingsCard from "../components/AtlassianSettingsCard.jsx";
import FigmaSettingsCard from "../components/FigmaSettingsCard.jsx";
import SmtpSettingsCard from "../components/SmtpSettingsCard.jsx";
import S3SettingsCard from "../components/S3SettingsCard.jsx";
import DatabaseSettingsCard from "../components/DatabaseSettingsCard.jsx";
import SyncSettingsCard from "../components/SyncSettingsCard.jsx";
import useConfiguration from "../hooks/useConfiguration.js";

/**
 * Configuration screen (was 06-configuration.js). Settings load when the
 * screen opens (window.loadConfig, see useConfiguration); each card saves its
 * own section and the whole screen re-reads the settings afterwards.
 */
export default function ConfigurationPage() {
  const cfg = useConfiguration();
  const card = { settings: cfg.settings, version: cfg.version, saveSettings: cfg.saveSettings };
  return (
    <section id="view-config" className="view" hidden>
      <div className="cfg-grid">
        <LlmSettingsCard {...card} />
        <EmbeddingSettingsCard {...card} loadConfig={cfg.loadConfig} />
        <AtlassianSettingsCard {...card} />
        <FigmaSettingsCard {...card} />
        <SmtpSettingsCard {...card} />
        <S3SettingsCard {...card} />
        <DatabaseSettingsCard db={cfg.db} loadDbStatus={cfg.loadDbStatus} />
        <SyncSettingsCard {...card} />
      </div>
    </section>
  );
}
