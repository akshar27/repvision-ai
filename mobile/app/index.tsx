import { useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Link, useRouter } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { ExerciseId, Preset, submitAnalysis } from "../src/api";
import { c } from "../src/theme";

const EXERCISES: { id: ExerciseId; label: string; tip: string }[] = [
  { id: "squat", label: "Squat", tip: "Film from the side or ~45°, head to feet in frame, camera at hip height, 2–3 m away." },
  { id: "pushup", label: "Push-up", tip: "Film from the side at floor/hip height with head to feet visible." },
  { id: "pullup", label: "Pull-up", tip: "Film from the front, level camera, arms and head visible. Without a marked bar, reps are labelled uncertain." },
];
const PRESETS: Preset[] = ["lenient", "standard", "strict"];

export default function Home() {
  const router = useRouter();
  const [exercise, setExercise] = useState<ExerciseId>("squat");
  const [preset, setPreset] = useState<Preset>("standard");
  const [busy, setBusy] = useState(false);

  async function go(source: "camera" | "library") {
    const perm = source === "camera"
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return Alert.alert("Permission needed", `Allow ${source} access in Settings to continue.`);
    const opts: ImagePicker.ImagePickerOptions = {
      mediaTypes: ["videos"], videoMaxDuration: 120,
      // Phone videos are often 4K/hundreds of MB; 720p is plenty for pose estimation and uploads far faster.
      videoExportPreset: ImagePicker.VideoExportPreset.H264_1280x720,
    };
    const res = source === "camera" ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
    if (res.canceled || !res.assets[0]) return;
    const a = res.assets[0];
    const ext = (a.fileName?.split(".").pop() ?? a.uri.split(".").pop() ?? "mp4").toLowerCase();
    setBusy(true);
    try {
      const id = await submitAnalysis(exercise, preset, {
        uri: a.uri, name: `set.${ext}`, type: a.mimeType ?? (ext === "mov" ? "video/quicktime" : "video/mp4"),
      });
      router.push({ pathname: "/results/[id]", params: { id } });
    } catch (e) {
      Alert.alert("Upload failed", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const tip = EXERCISES.find((e) => e.id === exercise)!.tip;
  return (
    <ScrollView contentContainerStyle={s.page}>
      <Text style={s.h}>Count reps from a video</Text>
      <Text style={s.p}>Pose estimation → joint angles → a rep state machine. No AI guessing of counts.</Text>

      <Text style={s.label}>Exercise</Text>
      <View style={s.row}>
        {EXERCISES.map((e) => (
          <Chip key={e.id} on={exercise === e.id} onPress={() => setExercise(e.id)}>{e.label}</Chip>
        ))}
      </View>
      <Text style={s.tip}>{tip}</Text>

      <Text style={s.label}>Sensitivity</Text>
      <View style={s.row}>
        {PRESETS.map((p) => <Chip key={p} on={preset === p} onPress={() => setPreset(p)}>{p}</Chip>)}
      </View>

      <Pressable style={[s.btn, busy && s.dis]} disabled={busy} onPress={() => go("camera")}>
        <Text style={s.btnT}>Record a set</Text>
      </Pressable>
      <Pressable style={[s.btn, s.ghost, busy && s.dis]} disabled={busy} onPress={() => go("library")}>
        <Text style={[s.btnT, { color: c.accent }]}>Choose a video</Text>
      </Pressable>
      {busy && <View style={s.row}><ActivityIndicator color={c.accent} /><Text style={s.p}>  Uploading…</Text></View>}

      <Link href="/settings" style={s.link}>Server settings</Link>
      <Text style={s.fine}>Not a medical tool. Feedback is estimated from 2D pose and describes measured angles only.</Text>
    </ScrollView>
  );
}

function Chip({ on, onPress, children }: { on: boolean; onPress: () => void; children: string }) {
  return (
    <Pressable onPress={onPress} style={[s.chip, on && s.chipOn]}>
      <Text style={[s.chipT, on && { color: c.bg }]}>{children}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  page: { padding: 20, gap: 12 },
  h: { color: c.text, fontSize: 26, fontWeight: "700" },
  p: { color: c.muted, fontSize: 14 },
  label: { color: c.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1, marginTop: 8 },
  row: { flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" },
  chip: { borderWidth: 1, borderColor: c.border, backgroundColor: c.card, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 999 },
  chipOn: { backgroundColor: c.accent, borderColor: c.accent },
  chipT: { color: c.text, textTransform: "capitalize", fontWeight: "600" },
  tip: { color: c.muted, fontSize: 13 },
  btn: { backgroundColor: c.accent, padding: 16, borderRadius: 12, alignItems: "center", marginTop: 8 },
  ghost: { backgroundColor: "transparent", borderWidth: 1, borderColor: c.accent },
  dis: { opacity: 0.5 },
  btnT: { color: c.bg, fontWeight: "700", fontSize: 16 },
  link: { color: c.accent, marginTop: 16, textAlign: "center" },
  fine: { color: c.muted, fontSize: 11, textAlign: "center", marginTop: 8 },
});
