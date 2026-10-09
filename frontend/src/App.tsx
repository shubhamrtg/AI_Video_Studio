import { useState, useEffect } from 'react';
import axios from 'axios';
import { Play, Loader2, FileSpreadsheet, Wand2, RefreshCw } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api';

function App() {
  const [queue, setQueue] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchQueue = async () => {
    try {
      const res = await axios.get(`${API_BASE}/orchestration/queue`);
      setQueue(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, 5000);
    return () => clearInterval(interval);
  }, []);

  const triggerIngest = async () => {
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/orchestration/ingest`);
      await fetchQueue();
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const getStatusColor = (status: string) => {
    switch(status) {
      case 'COMPLETED': return 'bg-green-500/20 text-green-400';
      case 'QUEUED': return 'bg-slate-700/50 text-slate-300';
      case 'FAILED': return 'bg-red-500/20 text-red-400';
      default: return 'bg-blue-500/20 text-blue-400'; // SCRIPTING, STORYBOARDING, etc.
    }
  };

  return (
    <div className="min-h-screen bg-[#0f1115] text-slate-200 p-8 font-sans">
      <header className="max-w-6xl mx-auto flex items-center justify-between mb-12">
        <div className="flex items-center gap-3">
          <Wand2 className="w-8 h-8 text-purple-500" />
          <h1 className="text-2xl font-bold">AI Video Production Orchestrator</h1>
        </div>
        <button 
          onClick={triggerIngest}
          disabled={loading}
          className="bg-purple-600 hover:bg-purple-700 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <RefreshCw className="w-5 h-5" />}
          Ingest from Excel
        </button>
      </header>

      <main className="max-w-6xl mx-auto space-y-8">
        <div className="bg-slate-900 rounded-xl border border-slate-800 shadow-xl overflow-hidden">
          <div className="p-6 border-b border-slate-800 flex items-center gap-3">
            <FileSpreadsheet className="w-6 h-6 text-green-500" />
            <h2 className="text-xl font-semibold">Production Queue</h2>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-950/50">
                  <th className="p-4 text-sm font-medium text-slate-400 border-b border-slate-800">Excel ID</th>
                  <th className="p-4 text-sm font-medium text-slate-400 border-b border-slate-800">Video Idea</th>
                  <th className="p-4 text-sm font-medium text-slate-400 border-b border-slate-800">Duration</th>
                  <th className="p-4 text-sm font-medium text-slate-400 border-b border-slate-800">Status</th>
                  <th className="p-4 text-sm font-medium text-slate-400 border-b border-slate-800">Actions</th>
                </tr>
              </thead>
              <tbody>
                {queue.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-8 text-center text-slate-500">
                      No projects found. Add ideas to video_ideas.xlsx and click Ingest.
                    </td>
                  </tr>
                ) : (
                  queue.map((project) => (
                    <tr key={project.id} className="hover:bg-slate-800/50 transition-colors border-b border-slate-800/50">
                      <td className="p-4 font-mono text-sm text-slate-400">{project.excel_id}</td>
                      <td className="p-4">
                        <div className="text-sm font-medium text-slate-200 line-clamp-2" title={project.video_idea}>
                          {project.video_idea}
                        </div>
                        <div className="text-xs text-slate-500 mt-1">Project ID: {project.id.split('-')[0]}...</div>
                      </td>
                      <td className="p-4 text-sm text-slate-300">{project.target_duration}s ({project.aspect_ratio})</td>
                      <td className="p-4">
                        <span className={`px-2.5 py-1 rounded-full text-xs font-medium tracking-wide ${getStatusColor(project.status)}`}>
                          {project.status}
                        </span>
                      </td>
                      <td className="p-4">
                        <button className="text-blue-400 hover:text-blue-300 text-sm font-medium flex items-center gap-1">
                          <Play className="w-4 h-4" /> Details
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
