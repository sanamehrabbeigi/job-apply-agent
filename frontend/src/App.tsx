import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { JobsPage } from "./components/JobsPage";
import { SearchDrawer } from "./components/SearchDrawer";
import { SettingsPage } from "./components/SettingsPage";
import { SetupBanners, TopBar, type Page } from "./components/TopBar";
import { useEvents } from "./hooks/useEvents";
import { applyRunEvent, type LiveRun } from "./lib/runs";
import type { AppEvent, Status } from "./types";

export default function App() {
  const [page, setPage] = useState<Page>("jobs");
  const [status, setStatus] = useState<Status | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [live, setLive] = useState<LiveRun | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(() => {
    api.status().then(setStatus).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(loadStatus, [loadStatus]);

  useEvents(
    useCallback(
      (event: AppEvent) => {
        if (!event.type.startsWith("run.")) return;
        setLive((prev) => applyRunEvent(prev, event));
        if (event.type === "run.source" || event.type === "run.finished") setRefreshKey((k) => k + 1);
        if (event.type === "run.finished") loadStatus();
      },
      [loadStatus],
    ),
  );

  const startSearch = async () => {
    setError(null);
    setDrawerOpen(true);
    try {
      await api.startSearch();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="app">
      <TopBar page={page} onNavigate={setPage} status={status} live={live} onSearch={() => void startSearch()} onShowRuns={() => setDrawerOpen(true)} />
      {error && (
        <div className="banner banner-error" role="alert">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
      {status && <SetupBanners status={status} onOpenSettings={() => setPage("settings")} />}
      <main>
        {page === "jobs" ? (
          <JobsPage refreshKey={refreshKey} />
        ) : (
          <SettingsPage
            onSaved={() => {
              loadStatus();
              setRefreshKey((k) => k + 1);
            }}
          />
        )}
      </main>
      {drawerOpen && <SearchDrawer live={live} onClose={() => setDrawerOpen(false)} />}
    </div>
  );
}
