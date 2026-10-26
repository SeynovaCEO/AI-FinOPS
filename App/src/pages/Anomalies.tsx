import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PageSkeleton } from "@/components/ui/Skeletons";
import { SeverityBadge } from "@/components/ui/StatusBadge";
import { Sparkline } from "@/components/charts/Sparkline";
import { cn } from "@/lib/utils";
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, ZAxis } from "recharts";

type StatusFilter = "active" | "acknowledged" | "resolved";
type Severity = "Critical" | "High" | "Medium" | "Low";

/** Shape returned by GET /api/anomalies (Decimal fields arrive as strings). */
interface ApiAnomaly {
  id: string;
  service: string;
  severity: Severity;
  spike: string | number;
  description: string;
  detected_at: string;
  data: number[];
  status: "open" | "acknowledged" | "resolved";
}

const STATUS_TO_FILTER: Record<ApiAnomaly["status"], StatusFilter> = {
  open: "active",
  acknowledged: "acknowledged",
  resolved: "resolved",
};

export default function Anomalies() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<StatusFilter>("active");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["anomalies"],
    queryFn: () => api.get<ApiAnomaly[]>("/anomalies"),
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "acknowledge" | "resolve" }) =>
      api.put<ApiAnomaly>(`/anomalies/${id}/${action}`),
    onSuccess: (_, { action }) => {
      queryClient.invalidateQueries({ queryKey: ["anomalies"] });
      toast.success(action === "acknowledge" ? "Anomaly acknowledged" : "Anomaly resolved");
    },
    onError: () => toast.error("Could not update anomaly. Please try again."),
  });

  if (isLoading) return <PageSkeleton />;
  if (isError || !data) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Could not load anomalies. Please refresh the page.</p>;
  }

  const anomalies = data
    .map((a) => ({
      ...a,
      spike: Number(a.spike),
      detectedAt: a.detected_at,
      displayStatus: STATUS_TO_FILTER[a.status],
    }))
    .sort((a, b) => new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime());

  const filtered = anomalies.filter((a) => a.displayStatus === filter);
  const sevCounts: Record<Severity, number> = { Critical: 0, High: 0, Medium: 0, Low: 0 };
  anomalies.filter((a) => a.displayStatus === "active").forEach((a) => sevCounts[a.severity]++);

  const scatterData = anomalies.map((a, i) => ({
    x: i,
    y: a.spike,
    severity: a.severity,
    service: a.service,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Anomaly Detection</h1>

      <div className="finops-card border-destructive/20 bg-destructive/5 p-5">
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <p className="text-xs uppercase tracking-wider text-destructive">Active Anomalies</p>
            <p className="text-3xl font-bold text-destructive">{anomalies.filter((a) => a.displayStatus === "active").length}</p>
          </div>
          <div className="flex gap-3">
            {(["Critical", "High", "Medium", "Low"] as const).map((s) => (
              <div key={s} className="text-center">
                <p className="text-lg font-bold">{sevCounts[s]}</p>
                <SeverityBadge severity={s} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex gap-1 rounded-lg bg-accent p-1">
        {(["active", "acknowledged", "resolved"] as StatusFilter[]).map((s) => (
          <button key={s} onClick={() => setFilter(s)} className={cn("rounded-md px-4 py-2 text-sm font-medium capitalize transition-all", filter === s ? "bg-card shadow-sm" : "text-muted-foreground")}>
            {s}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {filtered.map((a) => (
          <div key={a.id} className="finops-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-3">
                  <p className="font-semibold">{a.service}</p>
                  <SeverityBadge severity={a.severity} />
                </div>
                <p className="text-xs text-muted-foreground">{new Date(a.detectedAt).toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">{a.description}</p>
              </div>
              <div className="text-right space-y-2">
                <p className="text-3xl font-bold text-destructive">+{a.spike}%</p>
                <div className="w-24"><Sparkline data={a.data} color="hsl(var(--destructive))" /></div>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              {a.displayStatus === "active" && (
                <>
                  <button disabled={updateStatus.isPending} onClick={() => updateStatus.mutate({ id: a.id, action: "acknowledge" })} className="rounded-md bg-warning/10 px-3 py-1 text-xs font-medium text-warning hover:bg-warning/20 disabled:opacity-50">Acknowledge</button>
                  <button disabled={updateStatus.isPending} onClick={() => updateStatus.mutate({ id: a.id, action: "resolve" })} className="rounded-md bg-success/10 px-3 py-1 text-xs font-medium text-success hover:bg-success/20 disabled:opacity-50">Resolve</button>
                </>
              )}
              {a.displayStatus === "acknowledged" && (
                <button disabled={updateStatus.isPending} onClick={() => updateStatus.mutate({ id: a.id, action: "resolve" })} className="rounded-md bg-success/10 px-3 py-1 text-xs font-medium text-success hover:bg-success/20 disabled:opacity-50">Resolve</button>
              )}
              <button className="rounded-md bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20">Investigate</button>
            </div>
          </div>
        ))}
        {filtered.length === 0 && <p className="py-8 text-center text-sm text-muted-foreground">No {filter} anomalies</p>}
      </div>

      <div className="finops-card p-5">
        <h3 className="mb-4 text-sm font-semibold">Anomaly Timeline</h3>
        <ResponsiveContainer width="100%" height={200}>
          <ScatterChart>
            <XAxis type="number" dataKey="x" tick={false} stroke="hsl(var(--muted-foreground))" />
            <YAxis dataKey="y" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" label={{ value: "Spike %", angle: -90, position: "insideLeft", style: { fontSize: 11 } }} />
            <ZAxis range={[100, 400]} />
            <Tooltip content={({ payload }) => {
              if (!payload?.length) return null;
              const d = payload[0].payload;
              return <div className="rounded-lg border bg-card p-2 text-xs shadow-lg"><p className="font-medium">{d.service}</p><p className="text-muted-foreground">Spike: +{d.y}%</p></div>;
            }} />
            <Scatter data={scatterData} fill="hsl(var(--destructive))" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
