import MarsMap from "./components/MarsMap";

export default function App() {
  return (
    <main className="app">
      <header className="app-header">
        <div><p className="eyebrow">A-STELLAR / F1.5</p><h1>Mars explorer</h1></div>
        <p>NASA Mars Trek · Global MOLA color hillshade</p>
      </header>
      <MarsMap />
    </main>
  );
}
