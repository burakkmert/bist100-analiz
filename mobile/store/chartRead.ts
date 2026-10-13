// Yorumlanacak görüntüyü ekranlar arasında taşır (büyük base64 metni adres parametresine sığmaz).
import { create } from 'zustand';

interface ChartReadState {
  image: string | null;
  code: string | null;
  /** Görüntü nereden geldi: uygulama içi grafik mi, kullanıcının yüklediği mi */
  source: 'app' | 'upload' | null;
  set: (image: string, code: string | null, source: 'app' | 'upload') => void;
  clear: () => void;
}

export const useChartRead = create<ChartReadState>((set) => ({
  image: null,
  code: null,
  source: null,
  set: (image, code, source) => set({ image, code, source }),
  clear: () => set({ image: null, code: null, source: null }),
}));
