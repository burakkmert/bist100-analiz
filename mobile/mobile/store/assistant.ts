// Asistan sohbet durumu (cihazda kalıcı değil; uygulama kapanınca sıfırlanır).
import { create } from 'zustand';

import { streamAI } from '@/api/ai';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  /** data:image/...;base64 ya da dosya URI'si */
  image?: string;
  error?: boolean;
  /** Cevap hâlâ akıyor mu */
  streaming?: boolean;
}

export interface ScreenContext {
  screen: 'home' | 'markets' | 'portfolio' | 'settings' | 'asset_detail';
  code?: string;
}

interface AssistantState {
  messages: ChatMessage[];
  loading: boolean;
  /** Balona dokunulduğu anda alınan ekran görüntüsü */
  lastScreen: string | null;
  /** Balonun açıldığı ekran (sunucu bunu kullanarak analiz verisini isteme ekler) */
  context: ScreenContext | null;
  setContext: (c: ScreenContext | null) => void;
  setLastScreen: (uri: string | null) => void;
  send: (text: string, image?: string | null) => Promise<void>;
  clear: () => void;
}

const uid = () => Math.random().toString(36).slice(2, 10);

export const useAssistant = create<AssistantState>((set, get) => ({
  messages: [],
  loading: false,
  lastScreen: null,
  context: null,
  setContext: (context) => set({ context }),

  setLastScreen: (lastScreen) => set({ lastScreen }),

  send: async (text, image) => {
    const content = text.trim() || (image ? 'Bu görseli yorumlar mısın?' : '');
    if (!content || get().loading) return;

    const userMsg: ChatMessage = { id: uid(), role: 'user', text: content, image: image ?? undefined };
    set((s) => ({ messages: [...s.messages, userMsg], loading: true }));

    try {
      const history = get().messages
        .filter((m) => !m.error && !m.streaming)
        .slice(-12) // bağlamı kısa tut
        .map((m) => ({ role: m.role, content: m.text }));
      const id = uid();
      const update = (patch: Partial<ChatMessage>) =>
        set((s) => ({ messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) }));
      let started = false;

      const final = await streamAI({
        messages: history,
        image,
        context: get().context,
        onText: (full) => {
          if (!started) {
            // İlk parça gelince "yazıyor" noktaları yerini akan mesaja bırakır
            started = true;
            set((s) => ({ messages: [...s.messages, { id, role: 'assistant', text: full, streaming: true }] }));
          } else {
            update({ text: full });
          }
        },
      });
      if (started) update({ text: final, streaming: false });
      else set((s) => ({ messages: [...s.messages, { id, role: 'assistant', text: final || 'Yanıt boş geldi.' }] }));
    } catch (e) {
      set((s) => ({
        messages: [
          ...s.messages.map((m) => (m.streaming ? { ...m, streaming: false } : m)),
          {
            id: uid(),
            role: 'assistant',
            text: e instanceof Error ? `Yanıt alınamadı: ${e.message}` : 'Yanıt alınamadı.',
            error: true,
          },
        ],
      }));
    } finally {
      set({ loading: false });
    }
  },

  clear: () => set({ messages: [] }),
}));
