// İzleme listesi. Şimdilik cihazda saklanır; Kişi 2'nin /watchlist API'si hazır olunca
// add/remove içinde POST/DELETE çağrısı eklenecek (arayüz değişmez).
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

interface WatchlistState {
  codes: string[];
  toggle: (code: string) => void;
  has: (code: string) => boolean;
}

export const useWatchlist = create<WatchlistState>()(
  persist(
    (set, get) => ({
      codes: [],
      toggle: (code) =>
        set((s) => ({ codes: s.codes.includes(code) ? s.codes.filter((c) => c !== code) : [...s.codes, code] })),
      has: (code) => get().codes.includes(code),
    }),
    { name: 'fon-takip-watchlist', storage: createJSONStorage(() => AsyncStorage) },
  ),
);
