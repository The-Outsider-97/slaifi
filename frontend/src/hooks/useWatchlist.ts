import { useCallback } from "react";

import { addToWatchlist, fetchWatchlist, removeFromWatchlist } from "../services/finance";
import { useAction, useAsync } from "./useAsync";

/** The user's own list of followed assets, with live quotes where a source has them. */
export function useWatchlist() {
  const list = useAsync((signal) => fetchWatchlist(signal), "watchlist");
  const adder = useAction(addToWatchlist);
  const remover = useAction(removeFromWatchlist);
  const { reload } = list;
  const runAdd = adder.run;
  const runRemove = remover.run;

  const add = useCallback(
    async (symbol: string) => {
      const done = await runAdd(symbol);
      if (done !== null) reload();
    },
    [runAdd, reload],
  );
  const remove = useCallback(
    async (symbol: string) => {
      const done = await runRemove(symbol);
      if (done !== null) reload();
    },
    [runRemove, reload],
  );

  return {
    items: list.data?.items ?? [],
    loading: list.loading && !list.data,
    error: list.error,
    actionError: adder.error ?? remover.error,
    busy: adder.running || remover.running,
    reload,
    add,
    remove,
  };
}

export type Watchlist = ReturnType<typeof useWatchlist>;
