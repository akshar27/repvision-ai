import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useVideoPlayer, VideoView } from "expo-video";
import { AnalysisResult, getResult, videoUrl } from "../../src/api";
import { c } from "../../src/theme";

export default function Results() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [r, setR] = useState<AnalysisResult | null>(null);
  const [err, setErr] = useState("");
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    (async () => {
      while (!stop) {
        try {
          const res = await getResult(id);
          if (stop) return;
          setR(res);
          if (res.status === "completed" || res.status === "failed") return;
        } catch (e) {
          if (!stop) setErr(e instanceof Error ? e.message : String(e));
          return;
        }
        await new Promise((ok) => setTimeout(ok, 1500));
      }
    })();
    return () => { stop = true; };
  }, [id]);

  useEffect(() => {
    if (r?.status === "completed" && r.output_video?.available) videoUrl(id).then(setSrc);
  }, [r?.status, r?.output_video?.available, id]);

  if (err) return <Text style={s.err}>{err}</Text>;
  if (!r || r.status === "queued" || r.status === "processing") {
    return (
      <View style={s.center}>
        <ActivityIndicator color={c.accent} size="large" />
        <Text style={s.muted}>Analyzing… {Math.round((r?.progress ?? 0) * 100)}%</Text>
      </View>
    );
  }
  if (r.status === "failed") return <Text style={s.err}>Analysis failed: {r.error ?? "unknown error"}</Text>;

  return (
    <ScrollView contentContainerStyle={s.page}>
      <View style={s.row}>
        <Stat label="Full" n={r.summary.full} color={c.full} />
        <Stat label="Partial" n={r.summary.partial} color={c.partial} />
        <Stat label="Uncertain" n={r.summary.uncertain} color={c.uncertain} />
      </View>
      {src && <Player uri={src} />}
      {r.warnings.map((w, i) => <Text key={i} style={s.warn}>⚠ {w}</Text>)}

      <Text style={s.h}>Repetitions</Text>
      {r.reps.length === 0 && <Text style={s.muted}>No reps detected. Check camera angle and that your whole body is visible.</Text>}
      {r.reps.map((rep) => (
        <View key={rep.index} style={s.card}>
          <Text style={[s.rep, { color: c[rep.classification] }]}>
            #{rep.index} · {rep.classification} · {(rep.duration_ms / 1000).toFixed(1)}s
          </Text>
          {rep.feedback.map((f) => <Text key={f.code} style={s.muted}>• {f.message}</Text>)}
          <Text style={s.fine}>
            measurement confidence {Math.round(rep.measurement_confidence * 100)}% · heuristic classification confidence {Math.round(rep.classification_confidence * 100)}%
          </Text>
        </View>
      ))}
      <Text style={s.fine}>{r.disclaimer}</Text>
    </ScrollView>
  );
}

function Player({ uri }: { uri: string }) {
  const player = useVideoPlayer(uri, (p) => { p.loop = true; });
  return <VideoView player={player} style={s.video} nativeControls contentFit="contain" />;
}

function Stat({ label, n, color }: { label: string; n: number; color: string }) {
  return (
    <View style={s.stat}>
      <Text style={[s.n, { color }]}>{n}</Text>
      <Text style={s.muted}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  page: { padding: 20, gap: 12 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  row: { flexDirection: "row", gap: 10 },
  stat: { flex: 1, backgroundColor: c.card, borderColor: c.border, borderWidth: 1, borderRadius: 12, padding: 14, alignItems: "center" },
  n: { fontSize: 34, fontWeight: "800" },
  h: { color: c.text, fontSize: 18, fontWeight: "700", marginTop: 8 },
  card: { backgroundColor: c.card, borderColor: c.border, borderWidth: 1, borderRadius: 12, padding: 12, gap: 4 },
  rep: { fontWeight: "700", textTransform: "capitalize" },
  muted: { color: c.muted, fontSize: 13 },
  fine: { color: c.muted, fontSize: 11 },
  warn: { color: c.partial, fontSize: 13 },
  err: { color: c.uncertain, padding: 20, fontSize: 15 },
  video: { width: "100%", aspectRatio: 9 / 16, backgroundColor: "#000", borderRadius: 12 },
});
