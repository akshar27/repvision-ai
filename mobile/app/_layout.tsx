import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { c } from "../src/theme";

export default function Layout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{
        headerStyle: { backgroundColor: c.bg }, headerTintColor: c.text, headerShadowVisible: false,
        contentStyle: { backgroundColor: c.bg },
      }}>
        <Stack.Screen name="index" options={{ title: "RepVision AI" }} />
        <Stack.Screen name="settings" options={{ title: "Server" }} />
        <Stack.Screen name="results/[id]" options={{ title: "Results" }} />
      </Stack>
    </>
  );
}
