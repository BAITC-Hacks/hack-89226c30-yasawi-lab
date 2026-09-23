import { useEffect, useMemo, useState } from "react";
import { useForecast } from "./api/useForecast.js";
import { knownSteps, knownWarnings, languageOptions, translate } from "./i18n.js";

const HORIZON_HOURS = 48;
const DEFAULT_TIMEZONE = "Asia/Almaty";
const turbines = {
  turbine_1: { labelKey: "turbine1", color: "#147d73" },
  turbine_2: { labelKey: "turbine2", color: "#bd7448" },
};

const statusDetails = {
  idle: { tone: "neutral" },
  queued: { tone: "neutral" }, running: { tone: "blue" }, completed: { tone: "green" },
  partial: { tone: "amber" }, blocked: { tone: "amber" }, failed: { tone: "red" },
};

function formatTime(value, timeZone = DEFAULT_TIMEZONE, locale = "en-GB", options = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  try {
    return new Intl.DateTimeFormat(locale, {
      timeZone,
      day: "2-digit",
      month: locale === "kk-KZ" ? "2-digit" : "short",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      ...options,
    }).format(date);
  } catch {
    return "—";
  }
}

function formatDate(value, timeZone = DEFAULT_TIMEZONE, locale = "en-GB") {
  return formatTime(value, timeZone, locale, { year: "numeric", hour: undefined, minute: undefined });
}

function formatHour(value, timeZone = DEFAULT_TIMEZONE, locale = "en-GB") {
  return formatTime(value, timeZone, locale, { day: undefined, month: undefined });
}

function formattedNumber(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function StatusIcon({ status }) {
  if (status === "completed" || status === "ok") {
    return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m4.5 10 3.5 3.5 7.5-7.5" /></svg>;
  }
  if (status === "running" || status === "queued") {
    return <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" /><path d="M10 6v4l2.5 1.5" /></svg>;
  }
  if (status === "failed") {
    return <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" /><path d="m7.5 7.5 5 5m0-5-5 5" /></svg>;
  }
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5 18 17H2L10 2.5Z" /><path d="M10 7v4.5m0 2.5h.01" /></svg>;
}

function StatusPill({ status, t }) {
  const item = statusDetails[status] || statusDetails.failed;
  return <span className={`status-pill ${item.tone}`}><span className="status-dot" />{t(`status${status[0].toUpperCase()}${status.slice(1)}`)}</span>;
}

function LanguageSwitch({ language, onChange, t }) {
  return <div className="language-switch" role="group" aria-label={t("language")}>
    {languageOptions.map((option) => <button key={option.code} type="button" lang={option.code}
      className={language === option.code ? "active" : ""} aria-pressed={language === option.code}
      aria-label={`${t("language")}: ${option.label}`} onClick={() => onChange(option.code)}>{option.label}</button>)}
  </div>;
}

function localizedWarning(item, t) {
  const keys = knownWarnings[item.code];
  return keys ? { title: t(keys[0]), message: item.message || t(keys[1]) } : {
    title: item.code?.replaceAll("_", " ") || "—", message: item.message,
  };
}

function ForecastChart({ activeSeries, comparisonSeries, activeTurbine, timeZone, locale, t }) {
  const [hoverLead, setHoverLead] = useState(1);
  const width = 900;
  const height = 352;
  const plot = { left: 53, right: 20, top: 22, bottom: 52 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const validActive = activeSeries.filter((item) => Number.isFinite(item.power_normalized));
  const validComparison = comparisonSeries.filter((item) => Number.isFinite(item.power_normalized));
  const allValues = [...validActive, ...validComparison].map((item) => item.power_normalized);
  const axisMax = Math.max(1, Math.ceil(Math.max(...allValues, 0) * 4) / 4);
  const x = (lead) => plot.left + ((lead - 1) / (HORIZON_HOURS - 1)) * innerWidth;
  const y = (value) => plot.top + (1 - value / axisMax) * innerHeight;
  const line = (series) => series.map((item, index) =>
    `${index === 0 || item.lead_hours !== series[index - 1].lead_hours + 1 ? "M" : "L"}${x(item.lead_hours)},${y(item.power_normalized)}`
  ).join(" ");
  const contiguous = validActive.every((item, index) => index === 0 || item.lead_hours === validActive[index - 1].lead_hours + 1);
  const area = validActive.length && contiguous
    ? `${line(validActive)} L${x(validActive.at(-1).lead_hours)},${y(0)} L${x(validActive[0].lead_hours)},${y(0)} Z`
    : "";
  const active = validActive.find((item) => item.lead_hours === hoverLead) || validActive[0];
  const compared = validComparison.find((item) => item.valid_start === active?.valid_start);
  const xLabels = [1, 13, 25, 37, 48];
  const moveToPointer = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = ((event.clientX - bounds.left) / bounds.width) * width;
    const lead = Math.round(((position - plot.left) / innerWidth) * (HORIZON_HOURS - 1)) + 1;
    setHoverLead(Math.max(1, Math.min(HORIZON_HOURS, lead)));
  };

  return (
    <div className="chart-visual" tabIndex={0} aria-label={t("chartAria")}
      onKeyDown={(event) => {
        if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
          event.preventDefault();
          setHoverLead((lead) => Math.max(1, Math.min(HORIZON_HOURS, lead + (event.key === "ArrowRight" ? 1 : -1))));
        }
      }}>
      <span className="chart-mobile-hint">{t("chartMobileHint")}</span>
      <div className="chart-scroll"><svg viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={t("chartImageAria", { turbine: t(turbines[activeTurbine].labelKey) })}
        onPointerMove={moveToPointer} onPointerDown={moveToPointer}>
        <defs>
          <linearGradient id="forecast-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={turbines[activeTurbine].color} stopOpacity=".14" />
            <stop offset="100%" stopColor={turbines[activeTurbine].color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <g key={fraction}>
            <line className="chart-grid-line" x1={plot.left} x2={width - plot.right} y1={y(fraction * axisMax)} y2={y(fraction * axisMax)} />
            <text className="chart-axis-label" x={plot.left - 13} y={y(fraction * axisMax) + 4} textAnchor="end">{formattedNumber(fraction * axisMax)}</text>
          </g>
        ))}
        <line className="chart-day-divider" x1={x(25)} x2={x(25)} y1={plot.top} y2={y(0)} />
        <text className="chart-day-label" x={x(25) + 10} y={plot.top + 15}>{t("day2")}</text>
        {xLabels.map((lead) => {
          const row = validActive.find((item) => item.lead_hours === lead);
          return row ? <text key={lead} className="chart-axis-label" x={x(lead)} y={height - 17}
            textAnchor={lead === 1 ? "start" : lead === 48 ? "end" : "middle"}>{formatTime(row.valid_start, timeZone, locale)}</text> : null;
        })}
        {area && <path d={area} fill="url(#forecast-fill)" />}
        {validComparison.length > 0 && <path className="chart-comparison-line" d={line(validComparison)} />}
        <path className="chart-primary-line" d={line(validActive)} stroke={turbines[activeTurbine].color} />
        {active && (
          <g>
            <line className="chart-cursor-line" x1={x(active.lead_hours)} x2={x(active.lead_hours)} y1={plot.top} y2={y(0)} />
            <circle className="chart-cursor-halo" cx={x(active.lead_hours)} cy={y(active.power_normalized)} r="9" fill={turbines[activeTurbine].color} />
            <circle className="chart-cursor-dot" cx={x(active.lead_hours)} cy={y(active.power_normalized)} r="5" fill={turbines[activeTurbine].color} />
          </g>
        )}
        <rect x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} fill="transparent" />
      </svg></div>
      <div className="chart-inspector" aria-live="polite">
        <span>{active ? formatTime(active.valid_start, timeZone, locale) : t("noForecastHour")} <small>· {t("leadPlus", { lead: active?.lead_hours ?? "—" })}</small></span>
        <strong>{formattedNumber(active?.power_normalized)} <small>{t("normalizedPowerShort")}</small></strong>
        {compared && <span className="comparison-readout">{t("otherTurbine")} {formattedNumber(compared.power_normalized)}</span>}
      </div>
    </div>
  );
}

function EmptyForecast({ status, turbineLabel, errors = [], action = null, t }) {
  const key = status[0].toUpperCase() + status.slice(1);
  const title = t(`empty${key}Title`);
  const description = t(`empty${key}Desc`, { turbine: turbineLabel });
  const errorMessage = errors[0] ? localizedWarning(errors[0], t).message : null;
  return (
    <div className={`forecast-empty ${status}`} role="status">
      <span className="empty-icon"><StatusIcon status={status} /></span>
      <h3>{title}</h3>
      <p>{errorMessage || description}</p>
      {errors[0]?.code && <code>{errors[0].code}</code>}
      {action}
    </div>
  );
}

export function ForecastDashboard({ controller, initialLanguage }) {
  const { context, run, data: currentData, error: loadError, busy, originDate, setOriginDate,
    selectedOrigin, setSelectedOrigin, loadingDetail, execute, retryContext } = controller;
  const data = currentData || {};
  const [savedRunId, setSavedRunId] = useState("");
  const [activeTurbine, setActiveTurbine] = useState("turbine_1");
  const [language, setLanguage] = useState(() => {
    if (initialLanguage) return initialLanguage;
    try {
      const saved = window.localStorage.getItem("wind-replay-language");
      return languageOptions.some((option) => option.code === saved) ? saved : "ru";
    } catch {
      return "ru";
    }
  });
  const locale = languageOptions.find((option) => option.code === language)?.locale || "ru-RU";
  const t = (key, values) => translate(language, key, values);

  useEffect(() => {
    document.documentElement.lang = language;
    try { window.localStorage.setItem("wind-replay-language", language); } catch { /* Storage may be unavailable. */ }
  }, [language]);

  const originAt = data.origin_at || selectedOrigin || context?.origin_range?.first || null;
  const timeZone = context?.project_timezone || DEFAULT_TIMEZONE;
  const status = data.status || (busy || loadingDetail ? "running" : "idle");
  const originRows = useMemo(() =>
    (data?.forecasts || []).filter((row) => row.origin_at === originAt),
    [data, originAt]
  );
  const visibleRows = status === "completed" || status === "partial" ? originRows : [];
  const series = {
    turbine_1: visibleRows.filter((row) => row.turbine_id === "turbine_1").sort((a, b) => a.lead_hours - b.lead_hours),
    turbine_2: visibleRows.filter((row) => row.turbine_id === "turbine_2").sort((a, b) => a.lead_hours - b.lead_hours),
  };
  const activeSeries = series[activeTurbine];
  const comparisonSeries = series[activeTurbine === "turbine_1" ? "turbine_2" : "turbine_1"];
  const numericRows = activeSeries.filter((row) => Number.isFinite(row.power_normalized));
  const turbineSummary = data.summary?.per_turbine?.[activeTurbine];
  const mean = turbineSummary?.mean;
  const peak = turbineSummary?.max;
  const peakRow = peak === null ? null : numericRows.find((row) => row.power_normalized === peak);
  const totalCoverage = visibleRows.filter((row) => Number.isFinite(row.power_normalized)).length;
  const weatherId = activeSeries[0]?.weather_snapshot_id;
  const weather = data?.weather_snapshots?.find((snapshot) => snapshot.weather_snapshot_id === weatherId)
    || data?.weather_snapshots?.find((snapshot) => snapshot.turbine_id === activeTurbine);
  const requestedSite = weather?.requested_coordinate;
  const steps = data.agent?.steps || [];
  const warningList = data?.warnings || [];
  const errors = data?.errors || [];
  const revisionRows = activeSeries.filter((row) => Number.isFinite(row.revision_delta));
  const firstRevision = revisionRows[0];
  const turbineLabel = t(turbines[activeTurbine].labelKey);
  const turbineStatus = data.turbine_outcomes?.[activeTurbine] || status;
  const turbineErrors = errors.filter((item) => !item.details?.turbine_id || item.details.turbine_id === activeTurbine);
  const decisions = data.agent?.decisions || [];

  if (loadError && !context) {
    return <main className="app-shell"><header className="topbar"><strong className="brand-name">Wind Replay</strong><div className="topbar-right"><StatusPill status="failed" t={t} /><LanguageSwitch language={language} onChange={setLanguage} t={t} /></div></header>
      <div className="load-failure"><EmptyForecast status="failed" turbineLabel={turbineLabel} t={t}
        errors={[{ code: loadError.code || "API_UNAVAILABLE", message: loadError.message }]}
        action={<button className="retry-button" onClick={retryContext}>{t("retryLoading")}</button>} /></div></main>;
  }
  if (!context) {
    return <main className="app-shell"><header className="topbar"><strong className="brand-name">Wind Replay</strong><div className="topbar-right"><StatusPill status="running" t={t} /><LanguageSwitch language={language} onChange={setLanguage} t={t} /></div></header>
      <div className="initial-loading" role="status"><span className="loading-spinner" /><strong>{t("loadingTitle")}</strong><p>{t("loadingDescription")}</p></div></main>;
  }

  return (
    <main className="app-shell" id="top">
      <header className="topbar">
        <a className="brand" href="#top" aria-label={t("brandHome")}><span className="brand-symbol"><i /><i /><i /></span>
          <span><strong className="brand-name">Wind Replay</strong><small>{t("brandSubtitle")}</small></span></a>
        <div className="topbar-right">
          <span className="topbar-origin"><small>{t("replayOrigin")}</small><strong>{formatDate(originAt, timeZone, locale)} <span>{formatHour(originAt, timeZone, locale)}</span></strong></span>
          <StatusPill status={run?.status || status} t={t} />
          <LanguageSwitch language={language} onChange={setLanguage} t={t} />
        </div>
      </header>

      <section className="page-intro">
        <div>
          <div className="overline"><span className="overline-rule" />HACKALEM AI · ENERGY TRACK 01</div>
          <h1>{t("heading")}</h1>
          <p>{t("intro")}</p>
          <div className="mobile-origin"><span>{t("replayOrigin")}</span><strong>{formatDate(originAt, timeZone, locale)} · {formatHour(originAt, timeZone, locale)} {timeZone}</strong></div>
        </div>
        <div className="run-context">
          <span>{t("runId")} <code>{run?.run_id || "—"}</code></span>
        </div>
      </section>

      <section className="run-controls panel" aria-label={t("runControls")}>
        <form onSubmit={(event) => { event.preventDefault(); execute("single"); }}>
          <label>{t("runOrigin")}<input aria-label={t("runOrigin")} type="date" value={originDate}
            min={context.origin_range.first.slice(0, 10)} max={context.origin_range.last.slice(0, 10)}
            disabled={busy} required onChange={(event) => setOriginDate(event.target.value)} /></label>
          <button className="primary-button" disabled={busy || !originDate}>{t(busy ? "statusRunning" : "runForecast")}</button>
          <button type="button" disabled={busy || !context.capabilities?.replay} onClick={() => execute("replay")}>{t("runReplay")}</button>
        </form>
        <form onSubmit={(event) => { event.preventDefault(); execute("single", savedRunId.trim()); }}>
          <label>{t("savedRun")}<input aria-label={t("savedRun")} value={savedRunId} placeholder={t("runId")}
            pattern="[a-f0-9]{32}" required disabled={busy} onChange={(event) => setSavedRunId(event.target.value)} /></label>
          <button disabled={busy || !savedRunId.trim()}>{t("loadRun")}</button>
        </form>
      </section>
      {loadError && <div className="inline-notice red" role="alert"><StatusIcon status="failed" />
        <span><strong>{loadError.code || "API_UNAVAILABLE"}</strong> · {loadError.message}</span></div>}
      {run?.mode === "replay" && <section className="panel replay-summary" aria-label={t("replaySummary")}>
        <h2>{t("replaySummary")}</h2>
        <div className="replay-counts">{["total_origins", "success", "blocked", "failed", "with_farm_aggregate", "without_farm_aggregate"].map((key) =>
          <span key={key}>{t(key)} <strong>{run.summary?.[key] ?? (key === "total_origins" ? run.progress?.total_origins : "—")}</strong></span>)}</div>
        {!!run.origins?.length && <label>{t("viewOrigin")}<select value={selectedOrigin} aria-label={t("viewOrigin")}
          onChange={(event) => setSelectedOrigin(event.target.value)}>{run.origins.map((item) =>
            <option key={item.origin_at} value={item.origin_at}>{formatDate(item.origin_at, timeZone, locale)} · {t(`status${item.status[0].toUpperCase()}${item.status.slice(1)}`)}</option>)}</select></label>}
      </section>}

      <section className="kpi-strip" aria-label={t("overviewAria")}>
        <div className="kpi"><span>{t("forecastHorizon")}</span><strong>{context.horizon_hours} <small>{t("hours")}</small></strong><p>{t("hourlyIntervals")}</p></div>
        <div className="kpi"><span>{t("turbines")}</span><strong>{context.turbines.length} <small>{t("units")}</small></strong><p>{t("separateSeries")}</p></div>
        <div className="kpi"><span>{t(status === "blocked" ? "candidateWeatherRun" : "weatherRun")}</span>
          <strong className="kpi-date">{weather ? formatTime(weather.run_at_utc, "UTC", locale) : "—"} <small>UTC</small></strong>
          <p>{weather?.model || t("noRunRecorded")}</p></div>
        <div className="kpi"><span>{t("dataCoverage")}</span><strong>{totalCoverage} <small>/ {HORIZON_HOURS * 2} {t("hours")}</small></strong>
          <p>{t("rowsWithForecasts")}</p></div>
      </section>

      <section className="dashboard-grid">
        <article className="forecast-panel panel">
          <div className="panel-head chart-head">
            <div><span className="section-kicker">{t("generationForecast")}</span><h2>{t("normalizedPower")}</h2>
              <p>{t("next48")}</p></div>
            <div className="turbine-tabs" role="tablist" aria-label={t("selectTurbine")}>
              {context.turbines.map((site) => { const id = site.turbine_id; const turbine = turbines[id]; return (
                <button key={id} role="tab" aria-selected={activeTurbine === id}
                  className={activeTurbine === id ? "active" : ""} onClick={() => setActiveTurbine(id)}>
                  <span className="turbine-swatch" style={{ background: turbine.color }} />
                  <span>{t(turbine.labelKey)}<small>{site.dataset_id}</small></span>
                </button>
              ); })}
            </div>
          </div>

          {status === "partial" && <div className="inline-notice amber"><StatusIcon status="partial" />
            <span>{t("partialNotice")}</span></div>}
          {numericRows.length ? (
            <>
              <div className="chart-legend"><span><i style={{ background: turbines[activeTurbine].color }} />{turbineLabel}</span>
                {comparisonSeries.length > 0 && <span className="muted"><i />{t("otherTurbine")}</span>}</div>
              <ForecastChart activeSeries={activeSeries} comparisonSeries={comparisonSeries}
                activeTurbine={activeTurbine} timeZone={timeZone} locale={locale} t={t} />
              <div className="chart-summary">
                <div><span>{t("average")}</span><strong>{formattedNumber(mean)}</strong></div>
                <div><span>{t("peak")}</span><strong>{formattedNumber(peak)}</strong><small>{peakRow ? formatTime(peakRow.valid_start, timeZone, locale) : "—"}</small></div>
                <div><span>{t("availableHours")}</span><strong>{numericRows.length} <em>/ {HORIZON_HOURS}</em></strong></div>
              </div>
            </>
          ) : <EmptyForecast status={turbineStatus} turbineLabel={turbineLabel} errors={turbineErrors} t={t} />}
        </article>

        <aside className="evidence-column">
          <article className="panel agent-panel">
            <div className="panel-head"><div><span className="section-kicker">{t("autonomousWorkflow")}</span><h2>{t("agentExecution")}</h2></div></div>
            <p className="agent-description">{t(`desc${(statusDetails[status] ? status : "failed")[0].toUpperCase()}${(statusDetails[status] ? status : "failed").slice(1)}`)}</p>
            <ol className="agent-steps">
              {steps.map((step, index) => {
                const stepStatus = step.status === "error" ? "failed" : step.status === "not started" ? "queued" : step.status;
                return <li key={`${step.name}-${index}`} className={`step-${stepStatus}`}>
                  <span className="step-icon"><StatusIcon status={stepStatus} /></span>
                  <span><strong>{knownSteps[step.name] ? t(knownSteps[step.name]) : step.name}</strong>
                    <small>{t(`status${stepStatus[0].toUpperCase()}${stepStatus.slice(1)}`)}</small></span>
                </li>;
              })}
            </ol>
            <div className="agent-decision"><span>{t("recalculation")}</span><strong>
              {decisions.find((item) => item.action === "recalculate") ? t("revisionAvailable") :
                decisions.find((item) => item.action === "reuse_unchanged_calculation") ? t("unchangedInputs") :
                t(status === "running" ? "pendingAnalysis" : "noRevisionRecorded")}
            </strong></div>
            {decisions.length > 0 && <details className="decision-details"><summary>{t("agentDecisions")}</summary>
              {decisions.map((item, index) => <p key={index}><code>{item.action}</code> {item.reason || ""}</p>)}</details>}
          </article>

          <article className="panel evidence-panel">
            <div className="panel-head"><div><span className="section-kicker">{t("weatherEvidence")}</span><h2>{t("forecastProvenance")}</h2></div></div>
            {weather ? <>
              <dl className="evidence-list">
                <div><dt>{t("provider")}</dt><dd>{weather.provider}</dd></div>
                <div><dt>{t("model")}</dt><dd>{weather.model}</dd></div>
                <div><dt>{t("modelRun")}</dt><dd>{formatTime(weather.run_at_utc, "UTC", locale)} UTC</dd></div>
                <div><dt>{t("availabilityMethod")}</dt><dd>{weather.availability_method || t("notSupplied")}</dd></div>
                <div><dt>{t("availabilityBound")}</dt><dd>{formatTime(weather.available_by_utc, "UTC", locale)} UTC</dd></div>
                <div><dt>{t("runOrigin")}</dt><dd>{formatTime(weather.origin_utc, "UTC", locale)} UTC</dd></div>
                <div><dt>{t("weatherCoverage")}</dt><dd>{formatTime(weather.coverage_start_utc, "UTC", locale)} — {formatTime(weather.coverage_end_utc, "UTC", locale)} UTC</dd></div>
                <div><dt>{t("selectionReason")}</dt><dd>{weather.selection_reason || t("notSupplied")}</dd></div>
                <div><dt>{t("retrieved")}</dt><dd>{formatTime(weather.retrieved_at_utc, "UTC", locale)} UTC</dd></div>
                <div><dt>{t("variables")}</dt><dd>{weather.variables?.map((variable) =>
                  `${variable} · ${weather.hourly_units?.[variable] || "—"}`).join(" / ") || "—"}</dd></div>
                <div><dt>{t("requestedSite")}</dt><dd>{requestedSite
                  ? `${formattedNumber(requestedSite.latitude, 6)}, ${formattedNumber(requestedSite.longitude, 6)}` : t("notSupplied")}</dd></div>
                <div><dt>{t("gridPoint")}</dt><dd>{weather.provider_grid_coordinate
                  ? `${formattedNumber(weather.provider_grid_coordinate.latitude, 4)}, ${formattedNumber(weather.provider_grid_coordinate.longitude, 4)}` : "—"}</dd></div>
              </dl>
              <div className="provenance-foot"><span>{t("rawResponseHash")}</span><code title={weather.raw_sha256}>
                {weather.raw_sha256 ? `${weather.raw_sha256.slice(0, 18)}…` : t("notSupplied")}</code></div>
              {!weather.availability_evidence && <div className="evidence-caution">{t("availabilityMissing")}</div>}
              {weather.source_reference?.startsWith("https://") && <a className="source-link" href={weather.source_reference}
                target="_blank" rel="noreferrer">{t("viewWeatherSource")}</a>}
              {weather.availability_evidence?.source_urls?.filter((url) => url.startsWith("https://")).map((url) =>
                <a key={url} className="source-link" href={url} target="_blank" rel="noreferrer">{url.includes("ecmwf") ? "ECMWF" : "Open-Meteo"} · {t("availabilityMethod")} ↗</a>)}
            </> : <p className="empty-copy">{t("noWeatherSnapshot")}</p>}
          </article>

          <article className="panel warnings-panel">
            <div className="panel-head"><div><span className="section-kicker">{t("reviewNotes")}</span><h2>{t("warningsAssumptions")}</h2></div>
              <span className="count-badge">{warningList.length + errors.length}</span></div>
            <div className="warning-list">
              {[...errors, ...warningList].length ? [...errors, ...warningList].map((item, index) =>
                <div key={`${item.code}-${index}`} className="warning-row"><span className={`warning-mark ${item.severity || "error"}`} />
                  <span><strong title={item.code}>{localizedWarning(item, t).title}</strong><small>{localizedWarning(item, t).message}</small></span></div>
              ) : <p className="empty-copy">{t("noWarnings")}</p>}
            </div>
          </article>
        </aside>
      </section>

      <section className="bottom-grid">
        <article className="panel table-panel">
          <div className="panel-head"><div><span className="section-kicker">{t("hourlyOutput")}</span><h2>{t("turbineForecast", { turbine: turbineLabel })}</h2></div>
            <span className="table-count">{t("countHours", { count: numericRows.length, total: HORIZON_HOURS })}</span></div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>{t("localTime")}</th><th>{t("lead")}</th><th>{t("normalizedPower")}</th><th>{t("quality")}</th></tr></thead>
              <tbody>
                {activeSeries.map((item) =>
                  <tr key={`${item.origin_at}-${item.turbine_id}-${item.valid_start}`}>
                    <td><strong>{formatTime(item.valid_start, timeZone, locale)}</strong><small>{timeZone}</small></td>
                    <td>+{String(item.lead_hours).padStart(2, "0")} h</td>
                    <td>{Number.isFinite(item.power_normalized) && <span className="table-bar" style={{ width: `${item.power_normalized * 100}%`,
                      background: turbines[activeTurbine].color }} />}<strong>{formattedNumber(item.power_normalized)}</strong></td>
                    <td><span className={`quality-tag ${item.quality_flags?.length ? "flagged" : ""}`}>
                      {item.quality_flags?.length ? item.quality_flags.map((flag) => flag === "high-output-period" ? t("qualityHighOutput") : flag).join(", ") : t("noFlags")}</span></td>
                  </tr>
                )}
                {!activeSeries.length && <tr><td colSpan={4} className="no-rows">{t("noRows")}</td></tr>}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="details-column">
          <article className="panel detail-panel" aria-label={t("farmAggregate")}>
            <div className="panel-head"><div><span className="section-kicker">{t("farmAggregate")}</span>
              <h2>{Number.isFinite(data.farm_aggregate) ? formattedNumber(data.farm_aggregate) : t("aggregateUnavailable")}</h2></div></div>
            {!Number.isFinite(data.farm_aggregate) && <p className="detail-copy">{data.farm_aggregate_reason?.message || (currentData ? t("notSupplied") : t("emptyIdleDesc"))}
              {data.farm_aggregate_reason?.code && <><br /><code>{data.farm_aggregate_reason.code}</code></>}</p>}
          </article>
          <article className="panel detail-panel">
            <div className="panel-head"><div><span className="section-kicker">{t("runMetadata")}</span><h2>{t("modelSource")}</h2></div></div>
            <dl className="evidence-list">
              <div><dt>{t("forecastModel")}</dt><dd>{activeSeries[0]?.model_version || t("notAvailable")}</dd></div>
              <div><dt>{t("weatherSource")}</dt><dd>{weather?.provider || t("notAvailable")}</dd></div>
              <div><dt>{t("runOrigin")}</dt><dd>{formatTime(originAt, timeZone, locale)} {timeZone}</dd></div>
              <div><dt>{t("outputUnit")}</dt><dd>{t("normalizedPower")}</dd></div>
            </dl>
          </article>
          <article className="panel detail-panel">
            <div className="panel-head"><div><span className="section-kicker">{t("overlappingForecasts")}</span><h2>{t("revisionComparison")}</h2></div></div>
            {firstRevision ? <p className="detail-copy">{t("revisionSentence", { time: formatTime(firstRevision.valid_start, timeZone, locale),
              delta: formattedNumber(firstRevision.revision_delta), run: firstRevision.previous_run_id })}</p>
              : <p className="detail-copy">{t("noPreviousRevision")}</p>}
          </article>
        </aside>
      </section>

      <footer><span>WIND REPLAY · HACKALEM AI 2026</span><span>{t("footerNote")}</span></footer>
    </main>
  );
}

export default App;

function App() {
  const controller = useForecast();
  return <ForecastDashboard controller={controller} />;
}
