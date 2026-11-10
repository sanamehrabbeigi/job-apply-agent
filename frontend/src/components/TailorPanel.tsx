import { useEffect, useRef, useState } from "react";
import { api, fileUrl } from "../api";
import type { TailorState } from "../types";

export function TailorPanel({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const [state, setState] = useState<TailorState | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  const sessionId = state?.id;
  const active = state?.state === "running" || state?.state === "waiting";

  useEffect(() => {
    if (!active || !sessionId) return;
    const timer = window.setInterval(() => {
      api
        .tailor(sessionId)
        .then((next) => {
          setState(next);
          if (next.state === "done") onDoneRef.current();
        })
        .catch((e: Error) => setError(e.message));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, sessionId]);

  const start = async () => {
    setError(null);
    setAnswers({});
    try {
      setState(await api.startTailor(jobId));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const send = async (skip: boolean) => {
    if (!state) return;
    const list = skip ? [] : state.questions.map((q) => ({ question: q, answer: answers[q] ?? "" }));
    try {
      setState(await api.answer(state.id, list));
      setAnswers({});
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="tailor" aria-live="polite">
      <h3>Tailored resume</h3>
      {error && <p className="error" role="alert">{error}</p>}
      {!state && (
        <button className="primary" onClick={() => void start()}>Tailor my resume for this job</button>
      )}
      {state?.state === "running" && (
        <div>
          <p className="muted">Working… this usually takes a minute or two.</p>
          <ul className="progress-log">
            {state.progress.slice(-5).map((message, i) => (
              <li key={i}>{message}</li>
            ))}
          </ul>
        </div>
      )}
      {state?.state === "waiting" && (
        <form
          className="questions"
          onSubmit={(e) => {
            e.preventDefault();
            void send(false);
          }}
        >
          <p>Answer truthfully to raise the match, or skip. Answers are saved and reused for future jobs.</p>
          {state.questions.map((question) => (
            <label key={question}>
              {question}
              <textarea
                rows={2}
                value={answers[question] ?? ""}
                onChange={(e) => setAnswers({ ...answers, [question]: e.target.value })}
              />
            </label>
          ))}
          <div className="row">
            <button type="submit" className="primary">Send answers</button>
            <button type="button" onClick={() => void send(true)}>Skip</button>
          </div>
        </form>
      )}
      {state?.state === "done" && state.result && (
        <div>
          <p>
            <strong>Match {state.result.match_score}/100</strong> for {state.result.job_title}
            {state.result.company ? ` at ${state.result.company}` : ""}.
          </p>
          {state.result.missing_keywords.length > 0 && (
            <p className="muted">Not in your documents, so not added: {state.result.missing_keywords.join(", ")}</p>
          )}
          <ul>
            {state.result.files.map((file) => (
              <li key={file}>
                <a href={fileUrl(file)} download>{file.split("/").pop()}</a>
              </li>
            ))}
          </ul>
          {state.result.warnings.map((w) => (
            <p key={w} className="muted">{w}</p>
          ))}
          <p className="muted">Review every line before sending: it must be true and sound like you.</p>
          <button onClick={() => void start()}>Tailor again</button>
        </div>
      )}
      {state?.state === "error" && (
        <div>
          <p className="error">{state.error}</p>
          <button onClick={() => void start()}>Try again</button>
        </div>
      )}
    </section>
  );
}
