// Tema geçişinde yumuşak çapraz geçiş (crossfade) için durum.
// Akış: ekran görüntüsü alınır → en üste konur → görüntü ekrana oturunca tema değişir →
// yeni tema altta çizilir → görüntü yavaşça saydamlaşır → eski tema yenisine "erir".
import { create } from 'zustand';

interface ThemeFadeState {
  snapshot: string | null;
  /** Görüntü ekranda göründüğü an çalışacak iş (temayı değiştirmek) */
  onShown: (() => void) | null;
  start: (uri: string, onShown: () => void) => void;
  clear: () => void;
}

export const useThemeFade = create<ThemeFadeState>((set) => ({
  snapshot: null,
  onShown: null,
  start: (snapshot, onShown) => set({ snapshot, onShown }),
  clear: () => set({ snapshot: null, onShown: null }),
}));
