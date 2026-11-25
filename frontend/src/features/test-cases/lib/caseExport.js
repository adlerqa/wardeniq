/** Download a feature's test cases (all, or the given ids) as PDF / CSV (was downloadFeatureExport in 03). */
export async function downloadFeatureExport(featureId, format, ids, featureName) {
  const ext = format === "pdf" ? "pdf" : "csv";
  const mime = format === "pdf" ? "application/pdf" : "text/csv";
  const request = ids.length
    ? {
        url: `/api/features/${featureId}/export/${format}-selected`,
        init: { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ testCaseIds: ids }) },
      }
    : { url: `/api/features/${featureId}/export/${format}`, init: { method: "GET" } };
  const res = await fetch(request.url, request.init);
  if (!res.ok) {
    let detail = "Export failed";
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(featureName || "feature").replace(/[^a-z0-9]+/gi, "_").toLowerCase()}_test_cases.${ext}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
