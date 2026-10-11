// Portföy defteri. Uygulama işlem yapmaz; kullanıcı aracı kurumunda yaptığı işlemi buraya kaydeder.
// Şimdilik cihazda saklanır. Kişi 2'nin /portfolio API'si hazır olunca add/sell/remove içine
// POST/PATCH/DELETE çağrıları eklenecek; şekil openapi'deki Position ile aynı.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export interface Position {
  id: string;
  code: string;
  qty: number;
  buy_price: number;
  buy_date: string; // YYYY-MM-DD
  signal_id: string | null;
  sell_price: number | null;
  sell_date: string | null;
}

interface PortfolioState {
  positions: Position[];
  add: (p: Omit<Position, 'id' | 'sell_price' | 'sell_date'>) => string;
  sell: (id: string, sell_price: number, sell_date: string) => void;
  remove: (id: string) => void;
}

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

export const usePortfolio = create<PortfolioState>()(
  persist(
    (set) => ({
      positions: [],
      add: (p) => {
        const id = uid();
        set((s) => ({ positions: [{ ...p, id, sell_price: null, sell_date: null }, ...s.positions] }));
        return id;
      },
      sell: (id, sell_price, sell_date) =>
        set((s) => ({ positions: s.positions.map((x) => (x.id === id ? { ...x, sell_price, sell_date } : x)) })),
      remove: (id) => set((s) => ({ positions: s.positions.filter((x) => x.id !== id) })),
    }),
    { name: 'fon-takip-portfolio', storage: createJSONStorage(() => AsyncStorage) },
  ),
);
