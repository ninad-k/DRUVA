import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AccountState {
  /** The currently selected broker account scoping most pages. */
  activeAccountId: string | null;
  setActiveAccountId: (id: string | null) => void;
}

export const useAccountStore = create<AccountState>()(
  persist(
    (set) => ({
      activeAccountId: null,
      setActiveAccountId: (id) => set({ activeAccountId: id }),
    }),
    { name: "dhruva.account" },
  ),
);
