import { useCallback, useState } from "react";

/** [shown status (override or derived), setStatus(status, forVersion?)] */
export function useCardStatus(version, derived) {
  const [override, setOverride] = useState(null);
  const set = useCallback((status, forVersion) => setOverride({ ...status, ver: forVersion ?? version }), [version]);
  const shown = override && override.ver === version ? override : derived;
  return [shown, set];
}

/**
 * Card fields re-read from the settings whenever `version` changes;
 * `init(settings, loaded)` maps settings → fields (`loaded` is false before
 * the first load, when the static markup's empty fields show). Same-render
 * reset (no flash of old values).
 */
export function useSettingsForm(settings, version, init) {
  const [form, setForm] = useState(() => init(settings || {}, !!settings));
  const [seen, setSeen] = useState(version);
  if (seen !== version) {
    setSeen(version);
    setForm(init(settings || {}, !!settings));
  }
  const update = useCallback((patch) => setForm((f) => ({ ...f, ...patch })), []);
  return [form, update];
}

/** Save button label / disabled while a request runs. */
export function useBusy() {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn) => {
    setBusy(true);
    try {
      return await fn();
    } finally {
      setBusy(false);
    }
  }, []);
  return [busy, run];
}

/**
 * saveSection from 06-configuration.js: "Saving..." on the button, the
 * "Checking and saving settings..." status, PUT + reload, then the success
 * message (or the error, which is re-thrown for the card's toast).
 */
export function useSectionSave(version, saveSettings, setStatus) {
  const [busy, run] = useBusy();
  const save = useCallback(
    (body, successMessage = "Settings saved") =>
      run(async () => {
        setStatus({ tone: "", text: "Checking and saving settings...", saving: true }, version);
        try {
          const v = await saveSettings(body);
          setStatus({ tone: "ok", text: successMessage }, v);
          return v;
        } catch (e) {
          setStatus({ tone: "err", text: e.message }, version);
          throw e;
        }
      }),
    [run, saveSettings, setStatus, version],
  );
  return [busy, save];
}
