import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api, waitForJob } from "./api";
import { useApp } from "./app-context";

export function useSummary() {
  const { business } = useApp();
  return useQuery({ queryKey: ["summary", business], queryFn: () => api.summary(business || undefined) });
}

/** Runs an API action that starts a background job, then polls until done. */
export function useJob() {
  const qc = useQueryClient();
  const { t } = useApp();
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      const r = await waitForJob();
      if (r === "error") toast.error(t("jobError"));
    } catch {
      toast.error(t("jobError"));
    } finally {
      setBusy(false);
      qc.invalidateQueries();
    }
  };
  return { busy, run };
}

export function useAction<T>(fn: (v: T) => Promise<unknown>, success?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => { if (success) toast.success(success); qc.invalidateQueries(); },
  });
}
