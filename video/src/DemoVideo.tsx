import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";
import { ChatPanel } from "./ChatPanel";
import { ADMIN, CLIENT, INTRO, OUTRO, buildTimeline } from "./timeline";

const { fontFamily } = loadFont("normal", { weights: ["400", "600", "700"], subsets: ["latin", "cyrillic"] });
const FONT = `${fontFamily}, "Segoe UI Emoji", "Apple Color Emoji", sans-serif`;
const clampOpts = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const BOT_TITLE = "Поршень — консультант";

const FEATURES = [
  "Ответы по прайсу и условиям 24/7",
  "Не выдумывает: нет ответа — зовёт мастера",
  "Заявки с перепиской — сразу админу",
  "Мастер отвечает клиенту из Telegram",
  "Статистика и редактор базы знаний в боте",
];

export const DemoVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const tl = useMemo(() => buildTimeline(), []);
  const caption = [...tl.captions].reverse().find((c) => c.at <= frame);
  const outroStart = durationInFrames - OUTRO;
  const panelW = 800;
  const panelH = 830;

  const sceneOpacity = interpolate(frame, [INTRO - 12, INTRO, outroStart - 6, outroStart + 10], [0, 1, 1, 0], clampOpts);

  return (
    <AbsoluteFill style={{ background: "radial-gradient(circle at 30% 0%, #1d2b3a 0%, #0b121a 70%)", fontFamily: FONT }}>
      <style>{`.tg a{color:#6ab3f3;text-decoration:none}.tg b{font-weight:700}.tg i{color:#9fb2c4}.tg code{font-family:Consolas,monospace;color:#8fd3ff}`}</style>

      {/* Вступление */}
      <AbsoluteFill
        style={{
          justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 26,
          opacity: interpolate(frame, [0, 12, INTRO - 14, INTRO], [0, 1, 1, 0], clampOpts),
        }}
      >
        <div style={{ fontSize: 96, fontWeight: 700, color: "#fff", translate: interpolate(frame, [0, 20], ["0px 30px", "0px 0px"], { ...clampOpts, easing: Easing.bezier(0.16, 1, 0.3, 1) }) }}>
          AI-консультант для автосервиса
        </div>
        <div style={{ fontSize: 44, color: "#8fa6bd" }}>Telegram-бот · GigaChat · заявки · передача мастеру</div>
      </AbsoluteFill>

      {/* Основная сцена */}
      <AbsoluteFill style={{ opacity: sceneOpacity, padding: "56px 110px 40px", flexDirection: "column", gap: 26 }}>
        <div style={{ height: 70, display: "flex", alignItems: "center" }}>
          {caption ? (
            <div
              key={caption.at}
              style={{
                fontSize: 52, fontWeight: 700, color: "#fff",
                opacity: interpolate(frame - caption.at, [0, 10], [0, 1], clampOpts),
                translate: interpolate(frame - caption.at, [0, 12], ["0px 16px", "0px 0px"], { ...clampOpts, easing: Easing.bezier(0.16, 1, 0.3, 1) }),
              }}
            >
              {caption.text}
            </div>
          ) : null}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          {[CLIENT, ADMIN].map((chat) => (
            <ChatPanel
              key={chat}
              emptyHint={chat === ADMIN ? "Сюда придут заявки и вопросы клиентов" : undefined}
              title={BOT_TITLE}
              label={chat === CLIENT ? "Клиент" : "Мастер / админ"}
              items={tl.items.filter((i) => i.chat === chat)}
              typing={tl.typing[chat]}
              inputs={tl.inputs[chat]}
              replyKb={tl.replyKb[chat]}
              presses={tl.presses[chat]}
              width={panelW}
              height={panelH}
            />
          ))}
        </div>
      </AbsoluteFill>

      {/* Финал */}
      <AbsoluteFill
        style={{
          justifyContent: "center", paddingLeft: 220, flexDirection: "column", gap: 22,
          opacity: interpolate(frame, [outroStart + 4, outroStart + 18], [0, 1], clampOpts),
        }}
      >
        <div style={{ fontSize: 72, fontWeight: 700, color: "#fff", marginBottom: 20 }}>Что умеет бот</div>
        {FEATURES.map((f, i) => (
          <div
            key={f}
            style={{
              fontSize: 44, color: "#dbe6f0",
              opacity: interpolate(frame, [outroStart + 14 + i * 6, outroStart + 24 + i * 6], [0, 1], clampOpts),
              translate: interpolate(frame, [outroStart + 14 + i * 6, outroStart + 26 + i * 6], ["-24px 0px", "0px 0px"], { ...clampOpts, easing: Easing.bezier(0.16, 1, 0.3, 1) }),
            }}
          >
            <span style={{ color: "#6ab3f3" }}>✓</span> {f}
          </div>
        ))}
        <div style={{ fontSize: 30, color: "#7f91a4", marginTop: 30 }}>
          Ролик собран из реальных ответов бота · код: github.com/Slomi/AutoConsultBot
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
