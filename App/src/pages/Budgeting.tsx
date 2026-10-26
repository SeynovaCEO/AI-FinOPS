import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PageSkeleton } from "@/components/ui/Skeletons";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { formatCurrency } from "@/utils/format";
import { cn } from "@/lib/utils";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { toast } from "sonner";
import { Plus } from "lucide-react";

/** Shape returned by GET /api/budgets (Decimal fields arrive as strings). */
interface ApiBudget {
  id: string;
  name: string;
  owner: string;
  limit: string | number;
  spent: string | number;
  forecast: string | number;
  status: "Under Budget" | "At Risk" | "Exceeded";
}

const EMPTY_FORM = { name: "", owner: "", limit: "" };

export default function Budgeting() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["budgets"],
    queryFn: () => api.get<ApiBudget[]>("/budgets"),
  });

  const createBudget = useMutation({
    mutationFn: () =>
      api.post<ApiBudget>("/budgets/create", {
        name: form.name.trim(),
        owner: form.owner.trim(),
        limit: Number(form.limit),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["budgets"] });
      toast.success("Budget created");
      setShowModal(false);
      setForm(EMPTY_FORM);
    },
    onError: () => toast.error("Could not create budget. Please try again."),
  });

  if (isLoading) return <PageSkeleton />;
  if (isError || !data) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Could not load budgets. Please refresh the page.</p>;
  }

  const budgets = data.map((b) => ({
    ...b,
    limit: Number(b.limit),
    spent: Number(b.spent),
    forecast: Number(b.forecast),
  }));

  const statusVariant = (s: string) => s === "Under Budget" ? "success" : s === "At Risk" ? "warning" : "danger";
  const canCreate = form.name.trim() !== "" && form.owner.trim() !== "" && Number(form.limit) > 0;

  // Cumulative spend over a 30-day month at the current burn rate, against the pace that would exactly hit the combined limit
  const totalSpent = budgets.reduce((sum, b) => sum + b.spent, 0);
  const totalLimit = budgets.reduce((sum, b) => sum + b.limit, 0);
  const burnData = Array.from({ length: 30 }, (_, i) => ({
    day: i + 1,
    actual: Math.round((totalSpent / 30) * (i + 1)),
    ideal: Math.round((totalLimit / 30) * (i + 1)),
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Budgeting</h1>
        <button onClick={() => setShowModal(true)} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          <Plus size={16} /> Create Budget
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {budgets.map((b) => {
          const pct = Math.round((b.spent / b.limit) * 100);
          return (
            <div key={b.id} className="finops-card p-5 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold">{b.name}</p>
                  <p className="text-xs text-muted-foreground">{b.owner}</p>
                </div>
                <StatusBadge status={b.status} variant={statusVariant(b.status) as "success" | "warning" | "danger"} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div><span className="text-muted-foreground">Limit:</span> <span className="font-medium">{formatCurrency(b.limit)}</span></div>
                <div><span className="text-muted-foreground">Spent:</span> <span className="font-medium">{formatCurrency(b.spent)}</span></div>
              </div>
              <div>
                <div className="flex justify-between text-[10px] text-muted-foreground mb-1"><span>{pct}%</span><span>Forecast: {formatCurrency(b.forecast)}</span></div>
                <div className="h-2 rounded-full bg-muted">
                  <div className={cn("h-full rounded-full transition-all", pct >= 100 ? "bg-destructive" : pct >= 80 ? "bg-warning" : "bg-success")} style={{ width: `${Math.min(pct, 100)}%` }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="finops-card p-5">
        <h3 className="mb-4 text-sm font-semibold">Daily Burn Rate</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={burnData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
            <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
            <Tooltip formatter={(v: number) => formatCurrency(v)} contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="actual" name="Spend at current rate" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="ideal" name="Budget limit pace" stroke="hsl(var(--muted-foreground))" strokeWidth={1} strokeDasharray="5 5" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm" onClick={() => setShowModal(false)}>
          <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-4 text-lg font-semibold">Create Budget</h2>
            <div className="space-y-4">
              <div><label className="text-xs font-medium text-muted-foreground">Budget Name</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm" placeholder="Q2 Compute Budget" /></div>
              <div><label className="text-xs font-medium text-muted-foreground">Owner</label><input value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm" placeholder="Platform Engineering" /></div>
              <div><label className="text-xs font-medium text-muted-foreground">Limit ($)</label><input type="number" min="1" value={form.limit} onChange={(e) => setForm({ ...form, limit: e.target.value })} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm" placeholder="100000" /></div>
              <div className="flex gap-2 pt-2">
                <button disabled={!canCreate || createBudget.isPending} onClick={() => createBudget.mutate()} className="flex-1 rounded-lg bg-primary py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">{createBudget.isPending ? "Creating..." : "Create"}</button>
                <button onClick={() => setShowModal(false)} className="flex-1 rounded-lg bg-accent py-2 text-sm font-medium">Cancel</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
