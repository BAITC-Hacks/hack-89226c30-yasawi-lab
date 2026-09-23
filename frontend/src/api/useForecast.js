import { useCallback, useEffect, useRef, useState } from "react";
import { forecastApi } from "./forecast.js";

const pending = (run) => ["queued", "running"].includes(run?.status);

export function useForecast(client = forecastApi) {
  const [context, setContext] = useState(null);
  const [run, setRun] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [originDate, setOriginDate] = useState("");
  const [selectedOrigin, setSelectedOrigin] = useState("");
  const [loadingDetail, setLoadingDetail] = useState(false);
  const generation = useRef(0);
  const submitting = useRef(false);
  const timer = useRef(null);
  const controller = useRef(null);

  const loadContext = useCallback(async () => {
    setError(null);
    try {
      const value = await client.getContext();
      setContext(value);
      setOriginDate((current) => current || value.origin_range.first.slice(0, 10));
    } catch (err) { setError(err); }
  }, [client]);

  useEffect(() => { loadContext(); }, [loadContext]);
  useEffect(() => () => {
    generation.current += 1;
    controller.current?.abort();
    window.clearTimeout(timer.current);
  }, []);

  const poll = useCallback(async (runId, token) => {
    try {
      const value = await client.getRun(runId, { signal: controller.current.signal });
      if (token !== generation.current) return;
      setRun(value);
      setBusy(pending(value));
      if (pending(value)) timer.current = window.setTimeout(() => poll(runId, token), 2000);
    } catch (err) {
      if (token === generation.current && err.name !== "AbortError") { setError(err); setBusy(false); }
    }
  }, [client]);

  const execute = useCallback(async (mode, savedRunId = null) => {
    if (submitting.current || busy) return;
    submitting.current = true;
    const token = ++generation.current;
    window.clearTimeout(timer.current);
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true); setError(null); setRun(null); setDetail(null); setSelectedOrigin("");
    try {
      let runId = savedRunId;
      if (!runId) {
        const body = mode === "replay" ? { mode: "replay" } : {
          mode: "single", origin_at: `${originDate}T${context.origin_range.first.split("T")[1]}`,
        };
        if (context.configuration_id) body.configuration_id = context.configuration_id;
        const accepted = await client.createRun(body, { signal: controller.current.signal });
        runId = accepted.run_id;
      }
      if (token === generation.current) await poll(runId, token);
    } catch (err) {
      if (token === generation.current && err.name !== "AbortError") { setError(err); setBusy(false); }
    } finally { submitting.current = false; }
  }, [busy, client, context, originDate, poll]);

  const detailId = run?.mode === "replay" ? run.origins?.find((item) => item.origin_at === selectedOrigin)?.run_id : null;
  useEffect(() => {
    if (run?.mode === "replay" && run.origins?.length && !selectedOrigin) setSelectedOrigin(run.origins[0].origin_at);
  }, [run, selectedOrigin]);
  useEffect(() => {
    setDetail(null);
    if (!detailId) { setLoadingDetail(false); return; }
    const abort = new AbortController();
    setLoadingDetail(true);
    client.getRun(detailId, { signal: abort.signal }).then((value) => {
      if (!abort.signal.aborted) setDetail(value);
    }).catch((err) => {
      if (err.name !== "AbortError") setError(err);
    }).finally(() => { if (!abort.signal.aborted) setLoadingDetail(false); });
    return () => abort.abort();
  }, [client, detailId]);

  return { context, run, data: run?.mode === "replay" ? detail : run, error, busy,
    originDate, setOriginDate, selectedOrigin, setSelectedOrigin, loadingDetail,
    execute, retryContext: loadContext };
}
