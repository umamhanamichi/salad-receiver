'use strict';

const express = require('express');
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 4567;
const API_KEY = process.env.RECEIVER_API_KEY;

if (!API_KEY) {
  console.error('FATAL: RECEIVER_API_KEY env var not set');
  process.exit(1);
}

// In-memory store: machine_id -> node data
const nodes = new Map();

function requireApiKey(req, res, next) {
  if (req.headers['x-api-key'] !== API_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
}

function purgeStaleNodes() {
  const now = Date.now();
  for (const [id, node] of nodes.entries()) {
    if (now - new Date(node.last_seen).getTime() > 5 * 60 * 1000) {
      nodes.delete(id);
    }
  }
}

// POST /api/node/report
app.post('/api/node/report', requireApiKey, (req, res) => {
  const {
    machine_id, instance_id, armada, gpu_name,
    hashrate_1min, hashrate_15min, hashrate_1hr, hashrate_6hr,
    power_watt, country, min_th, timestamp
  } = req.body;

  if (!machine_id || !armada || !gpu_name) {
    return res.status(400).json({ error: 'machine_id, armada, gpu_name required' });
  }

  nodes.set(machine_id, {
    machine_id,
    instance_id: instance_id || '',
    armada,
    gpu_name,
    hashrate_1min: hashrate_1min || 0,
    hashrate_15min: hashrate_15min || 0,
    hashrate_1hr: hashrate_1hr || 0,
    hashrate_6hr: hashrate_6hr || 0,
    power_watt: power_watt || 0,
    country: country || 'UNKNOWN',
    min_th: min_th || 0,
    last_seen: timestamp || new Date().toISOString(),
    status: 'online'
  });

  console.log(`[report] ${armada} | ${machine_id} | ${gpu_name} | ${hashrate_1min} TH/s`);
  res.json({ ok: true });
});

// GET /api/nodes
app.get('/api/nodes', requireApiKey, (req, res) => {
  purgeStaleNodes();

  const nodeList = Array.from(nodes.values());

  const byArmada = {};
  for (const node of nodeList) {
    if (!byArmada[node.armada]) {
      byArmada[node.armada] = {
        node_count: 0,
        gpus: [],
        total_hashrate_1min: 0,
        avg_hashrate_1min: 0
      };
    }
    const a = byArmada[node.armada];
    a.node_count++;
    if (!a.gpus.includes(node.gpu_name)) a.gpus.push(node.gpu_name);
    a.total_hashrate_1min += node.hashrate_1min;
  }

  for (const armada of Object.values(byArmada)) {
    armada.avg_hashrate_1min = armada.node_count
      ? parseFloat((armada.total_hashrate_1min / armada.node_count).toFixed(2))
      : 0;
    armada.total_hashrate_1min = parseFloat(armada.total_hashrate_1min.toFixed(2));
  }

  res.json({
    nodes: nodeList,
    total: nodeList.length,
    by_armada: byArmada
  });
});

// GET /health
app.get('/health', (req, res) => {
  res.json({ ok: true, uptime: process.uptime() });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`vps-receiver listening on 0.0.0.0:${PORT}`);
});
