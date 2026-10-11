import { useEffect, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { getServer, health, setServer } from "../src/api";
import { c } from "../src/theme";

export default function Settings() {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => { getServer().then(setUrl); }, []);

  async function save() {
    try {
      await setServer(url);
      const h = await health(url.trim().replace(/\/+$/, ""));
      setStatus(`Connected. ffmpeg: ${h.ffmpeg ? "yes" : "no (annotated video may not play)"}, pose model: ${h.pose_model_present ? "ok" : "MISSING"}`);
    } catch (e) {
      setStatus("");
      Alert.alert("Not connected", e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <View style={s.page}>
      <Text style={s.p}>Address of the RepVision backend on your computer. Start it with:</Text>
      <Text style={s.code}>python3 scripts/run_local.py --lan</Text>
      <Text style={s.p}>Your phone and computer must be on the same Wi-Fi. Use the computer's LAN IP, e.g. http://192.168.1.20:8000.</Text>
      <TextInput value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" style={s.input} />
      <Pressable style={s.btn} onPress={save}><Text style={s.btnT}>Save & test connection</Text></Pressable>
      {!!status && <Text style={[s.p, { color: c.full }]}>{status}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  page: { padding: 20, gap: 12 },
  p: { color: c.muted, fontSize: 14 },
  code: { color: c.text, backgroundColor: c.card, padding: 10, borderRadius: 8, fontFamily: "Courier" },
  input: { color: c.text, backgroundColor: c.card, borderColor: c.border, borderWidth: 1, borderRadius: 10, padding: 12, fontSize: 16 },
  btn: { backgroundColor: c.accent, padding: 14, borderRadius: 12, alignItems: "center" },
  btnT: { color: c.bg, fontWeight: "700" },
});
