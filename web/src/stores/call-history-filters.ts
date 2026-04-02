/**
 * Zustand store for CallHistoryPage filter state (story-5-5).
 *
 * Slices:
 *   status    — tab filter: "all" | "missed" | "completed" | "needs-callback"
 *   dateRange — date chip: "today" | "week" | "month" | "all"
 *   page      — current page (1-based)
 *
 * Changing status or dateRange resets page to 1.
 */
import { create } from "zustand";

export type CallHistoryStatus = "all" | "missed" | "completed" | "needs-callback";
export type CallHistoryDateRange = "today" | "week" | "month" | "all";

interface CallHistoryFiltersState {
  status: CallHistoryStatus;
  dateRange: CallHistoryDateRange;
  page: number;

  setStatus: (status: CallHistoryStatus) => void;
  setDateRange: (dateRange: CallHistoryDateRange) => void;
  setPage: (page: number) => void;
}

export const useCallHistoryFilters = create<CallHistoryFiltersState>((set) => ({
  status: "all",
  dateRange: "all",
  page: 1,

  setStatus: (status) => set({ status, page: 1 }),
  setDateRange: (dateRange) => set({ dateRange, page: 1 }),
  setPage: (page) => set({ page }),
}));
