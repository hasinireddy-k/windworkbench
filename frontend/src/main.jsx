import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  Wind,
  Gauge,
  RefreshCw,
  ArrowUpRight,
  AlertTriangle,
  CheckCircle2,
  Zap,
  Clock,
  ShieldCheck,
  Calendar,
  Layers,
} from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const fmt = (v, d = 1) =>
  v == null || !Number.isFinite(Number(v))
    ? '—'
    : Number(v).toLocaleString('en-GB', {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      });

function App() {
  const [data, setData] = useState(null);
  const [decisionRules, setDecisionRules] = useState([]);
  const [decisionRule, setDecisionRule] = useState('day_ahead_d1_1700');
  const [resolution, setResolution] = useState('hourly');
  const [chartTab, setChartTab] = useState('timeseries'); // 'timeseries' or 'diurnal'
  const [errorFilter, setErrorFilter] = useState('all'); // 'all', 'over', 'under'
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');

  // Fetch supported decision rules on startup
  useEffect(() => {
    fetch(`${API}/api/decision-rules`)
      .then((r) => r.json())
      .then((j) => {
        if (j.rules) {
          const list = Object.entries(j.rules).map(([k, v]) => ({
            key: k,
            ...v,
          }));
          setDecisionRules(list);
        }
      })
      .catch((e) => console.warn('Could not load decision rules list:', e));
  }, []);

  async function loadData(forceRefresh = false) {
    setBusy(true);
    setError('');
    try {
      const url = `${API}/api/analysis?decision_rule=${decisionRule}&resolution=${resolution}${
        forceRefresh ? '&refresh=true' : ''
      }`;
      const r = await fetch(url);
      const j = await r.json();
      if (!r.ok) {
        throw new Error(j.detail || 'Elexon API request failed');
      }
      setData(j);
    } catch (e) {
      setError(
        `${e.message}. Check that the backend is running and the Elexon API is accessible.`
      );
    } finally {
      setBusy(false);
    }
  }

  // Reload when decision rule or resolution changes
  useEffect(() => {
    loadData(false);
  }, [decisionRule, resolution]);

  // Formatted chart points
  const chartPoints = useMemo(() => {
    return (data?.data || []).map((x) => {
      const d = new Date(x.startTime);
      return {
        ...x,
        label:
          d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) +
          ' ' +
          d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }),
      };
    });
  }, [data]);

  // Filtered largest errors
  const filteredErrors = useMemo(() => {
    const list = data?.largestErrors || [];
    if (errorFilter === 'over') return list.filter((x) => x.error > 0);
    if (errorFilter === 'under') return list.filter((x) => x.error < 0);
    return list;
  }, [data, errorFilter]);

  const met = data?.metrics || {};
  const counts = data?.counts || {};
  const isOverForecast = (met.biasMW || 0) > 0;

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brandIcon">
            <Wind size={22} />
          </div>
          <div>
            <b>WINDWORKS</b>
            <small>FORECAST INTELLIGENCE</small>
          </div>
        </div>

        <div className="navLabel">WORKSPACE</div>
        <div className="nav active">
          <Activity size={16} /> Overview <span>JAN 2026</span>
        </div>
        <div className="nav" onClick={() => setChartTab('timeseries')}>
          <Layers size={16} /> Generation Tracking
        </div>
        <div className="nav" onClick={() => setChartTab('diurnal')}>
          <Clock size={16} /> Diurnal Miss Profile
        </div>
        <div className="nav">
          <ShieldCheck size={16} /> Audit & Integrity
        </div>

        <div className="sideBottom">
          <i></i> ELEXON BMRS API
          <small>
            FUELHH + WINDFOR Streams
            <br />
            January 2026 Delivery
          </small>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main">
        <header>
          <div>
            <div className="eyebrow">ENERGY INTELLIGENCE / UK POWER MARKET</div>
            <h1>Wind Forecast Workbench</h1>
            <p className="sub">
              Quantitative forecast accuracy evaluation for UK energy utility day-ahead purchasing decisions.
              Eliminating look-ahead bias through strict decision-gate enforcement.
            </p>
          </div>
          <button className="refresh" onClick={() => loadData(true)} disabled={busy}>
            <RefreshCw size={15} className={busy ? 'spin' : ''} />
            {busy ? 'Fetching...' : 'Live Refresh'}
          </button>
        </header>

        {/* Toolbar & Filter Controls */}
        <div className="toolbar">
          <div className="toolbarGroup">
            <div>
              <i></i> EVALUATION WINDOW <b>01 — 31 JAN 2026</b>
            </div>

            <div className="toolbarSelect">
              <label>Decision Gate:</label>
              <select
                value={decisionRule}
                onChange={(e) => setDecisionRule(e.target.value)}
                disabled={busy}
              >
                {decisionRules.length > 0 ? (
                  decisionRules.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.name}
                    </option>
                  ))
                ) : (
                  <>
                    <option value="day_ahead_d1_1700">Day-Ahead (D-1 17:00 UTC - Standard)</option>
                    <option value="day_ahead_d1_1200">Day-Ahead Auction (D-1 12:00 UTC)</option>
                    <option value="day_ahead_d1_2359">Day-Ahead Midnight (D-1 23:59 UTC)</option>
                    <option value="rolling_24h">Rolling 24h Ahead</option>
                    <option value="latest_available">Latest Available (Look-Ahead Benchmark)</option>
                  </>
                )}
              </select>
            </div>

            <div className="toolbarSelect">
              <label>Resolution:</label>
              <div className="pills">
                <button
                  className={`pill ${resolution === 'hourly' ? 'active' : ''}`}
                  onClick={() => setResolution('hourly')}
                >
                  Hourly (Aggregated)
                </button>
                <button
                  className={`pill ${resolution === 'half_hourly' ? 'active' : ''}`}
                  onClick={() => setResolution('half_hourly')}
                >
                  Half-Hourly (Settlement)
                </button>
              </div>
            </div>
          </div>

          <div className="source">
            Source: Elexon BMRS Stream <ArrowUpRight size={14} />
          </div>
        </div>

        {/* Look-Ahead Bias Prevention Banner */}
        {data?.decisionRule && (
          <div className="ruleAlert">
            <ShieldCheck size={18} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <b>{data.decisionRule.name}:</b> {data.decisionRule.description}
              {decisionRule === 'latest_available' ? (
                <span style={{ color: '#ffbd88', marginLeft: 8 }}>
                  [Warning: Demonstrates look-ahead bias by incorporating intraday forecasts published after market gates.]
                </span>
              ) : (
                <span style={{ color: '#67e8c2', marginLeft: 8 }}>
                  [Look-ahead bias strictly eliminated: forecasts published after the decision cutoff are excluded.]
                </span>
              )}
            </div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="alert">
            <AlertTriangle size={20} />
            <div>
              <b>Elexon Data Retrieval Error</b>
              <p>{error}</p>
              <button onClick={() => loadData(true)}>Retry Connection</button>
            </div>
          </div>
        )}

        {/* Loading State */}
        {busy && !data && (
          <div className="loading">
            <RefreshCw size={24} className="spin" style={{ color: '#67e8c2' }} />
            <span>Connecting to Elexon BMRS API and evaluating January 2026 delivery intervals...</span>
          </div>
        )}

        {/* KPI Summary Cards */}
        <section className="kpis">
          <Metric
            label="MEAN ABSOLUTE ERROR"
            value={fmt(met.maeMW)}
            unit="MW"
            note="Average magnitude of deviation"
            icon={<Activity />}
          />
          <Metric
            label="ROOT MEAN SQUARED ERROR"
            value={fmt(met.rmseMW)}
            unit="MW"
            note="Quadratic penalty on large misses"
            icon={<Gauge />}
          />
          <Metric
            label="FORECAST BIAS"
            value={(met.biasMW > 0 ? '+' : '') + fmt(met.biasMW)}
            unit="MW"
            note={
              <span className={`badge ${isOverForecast ? 'over' : 'under'}`}>
                {isOverForecast ? 'Over-forecasting' : 'Under-forecasting'}
              </span>
            }
            icon={<Wind />}
          />
          <Metric
            label="WEIGHTED ABS ERROR (WAPE)"
            value={fmt(met.wapePercent)}
            unit="%"
            note="Energy trading industry standard"
            icon={<Zap />}
          />
          <Metric
            label="MATCHED COVERAGE"
            value={counts.matchedIntervals ? counts.matchedIntervals.toLocaleString('en-GB') : '—'}
            unit={`/ ${counts.expectedIntervals || '—'}`}
            note={
              <span className="badge success">
                {met.coveragePercent != null ? `${fmt(met.coveragePercent)}% Complete` : '—'}
              </span>
            }
            icon={<CheckCircle2 />}
          />
        </section>

        {/* Primary Chart: Forecast vs Actual or Diurnal Profile */}
        <section className="panel">
          <div className="panelHead">
            <div>
              <div className="eyebrow">
                01 / {chartTab === 'timeseries' ? 'GENERATION TRACKING' : 'DIURNAL HOURLY PROFILE'}
              </div>
              <h2>
                {chartTab === 'timeseries'
                  ? 'Wind Generation: Forecast vs Actual'
                  : 'Time-of-Day Miss Profile (Diurnal Distribution)'}
              </h2>
              <p>
                {chartTab === 'timeseries'
                  ? `Matched target intervals · ${resolution === 'hourly' ? '1-Hour Aligned' : 'Half-Hourly Settlement Periods'} · MW`
                  : 'Average generation and forecast error by hour of day (00:00 to 23:00 UTC)'}
              </p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div className="pills">
                <button
                  className={`pill ${chartTab === 'timeseries' ? 'active' : ''}`}
                  onClick={() => setChartTab('timeseries')}
                >
                  Time Series
                </button>
                <button
                  className={`pill ${chartTab === 'diurnal' ? 'active' : ''}`}
                  onClick={() => setChartTab('diurnal')}
                >
                  Diurnal 24h
                </button>
              </div>

              <div className="legend">
                <span>
                  <i className="forecast"></i> Forecast
                </span>
                <span>
                  <i className="actual"></i> Actual
                </span>
              </div>
            </div>
          </div>

          {chartTab === 'timeseries' ? (
            chartPoints.length ? (
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartPoints}>
                    <defs>
                      <linearGradient id="fGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#67e8c2" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#67e8c2" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="aGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#7da8ff" stopOpacity={0.2} />
                        <stop offset="100%" stopColor="#7da8ff" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1d2e42" />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: '#8092a9', fontSize: 10 }}
                      minTickGap={60}
                    />
                    <YAxis
                      tick={{ fill: '#8092a9', fontSize: 10 }}
                      width={55}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#101e30',
                        border: '1px solid #2b3b50',
                        borderRadius: 10,
                        color: '#eaf1f8',
                        fontSize: 12,
                      }}
                      formatter={(v, name) => [`${fmt(v)} MW`, name]}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="forecast"
                      name="Forecast (WINDFOR)"
                      stroke="#67e8c2"
                      fill="url(#fGrad)"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="actual"
                      name="Actual (FUELHH)"
                      stroke="#7da8ff"
                      fill="url(#aGrad)"
                      strokeWidth={2}
                      dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty busy={busy} error={error} />
            )
          ) : (
            // Diurnal 24h Profile Chart
            data?.diurnalProfile?.length ? (
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.diurnalProfile}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1d2e42" />
                    <XAxis dataKey="hour" tick={{ fill: '#8092a9', fontSize: 10 }} />
                    <YAxis
                      tick={{ fill: '#8092a9', fontSize: 10 }}
                      width={55}
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k MW`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#101e30',
                        border: '1px solid #2b3b50',
                        borderRadius: 10,
                        color: '#eaf1f8',
                        fontSize: 12,
                      }}
                      formatter={(v, name) => [`${fmt(v)} MW`, name]}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="forecastAvg"
                      name="Average Forecast"
                      stroke="#67e8c2"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="actualAvg"
                      name="Average Actual"
                      stroke="#7da8ff"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="mae"
                      name="Average MAE"
                      stroke="#ffbd88"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty busy={busy} error={error} />
            )
          )}
        </section>

        {/* Grid: Daily Error Profile & Quantitative Model Quality */}
        <div className="grid2">
          {/* Daily Error Profile */}
          <section className="panel">
            <div className="panelHead">
              <div>
                <div className="eyebrow">02 / DAILY ACCURACY TREND</div>
                <h2>Daily Mean Absolute Error</h2>
                <p>Tracking daily forecast misses across January 2026 (MW)</p>
              </div>
            </div>
            {data?.dailyProfile?.length ? (
              <div className="chart small">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.dailyProfile}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1d2e42" />
                    <XAxis
                      dataKey="day"
                      tick={{ fill: '#8092a9', fontSize: 9 }}
                      tickFormatter={(v) => v.slice(8)}
                    />
                    <YAxis tick={{ fill: '#8092a9', fontSize: 10 }} width={45} />
                    <Tooltip
                      contentStyle={{
                        background: '#101e30',
                        border: '1px solid #2b3b50',
                        borderRadius: 10,
                        color: '#eaf1f8',
                      }}
                      formatter={(v) => [`${fmt(v)} MW`, 'Daily MAE']}
                    />
                    <Bar dataKey="mae" name="Daily MAE (MW)" fill="#7da8ff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty busy={busy} error={error} />
            )}
          </section>

          {/* Model Quality & Integrity Breakdown */}
          <section className="panel">
            <div className="eyebrow">03 / QUANTITATIVE ACCURACY AUDIT</div>
            <h2>Evaluation Metrics & Integrity</h2>

            <div className="metricLine">
              <span>Weighted Absolute Percentage Error (WAPE)</span>
              <b>{met.wapePercent != null ? `${fmt(met.wapePercent)}%` : '—'}</b>
            </div>

            <div className="metricLine">
              <span>Symmetric MAPE (sMAPE)</span>
              <b>{met.smapePercent != null ? `${fmt(met.smapePercent)}%` : '—'}</b>
            </div>

            <div className="metricLine">
              <span>Normalized MAE (nMAE vs Mean Actual)</span>
              <b>{met.nmaePercent != null ? `${fmt(met.nmaePercent)}%` : '—'}</b>
            </div>

            <div className="metricLine">
              <span>Filtered MAPE (Actual ≥ 100 MW)</span>
              <b>
                {met.filteredMape?.mapePercent != null
                  ? `${fmt(met.filteredMape.mapePercent)}%`
                  : '—'}
              </b>
            </div>
            <p className="explain">
              Standard MAPE explodes when actual output approaches zero. Filtered MAPE evaluates points
              ≥ 100 MW ({met.filteredMape?.includedCount || 0} intervals included,{' '}
              {met.filteredMape?.excludedCount || 0} calm intervals excluded).
            </p>

            <div className="metricLine">
              <span>Mean Actual Generation</span>
              <b>{fmt(met.meanActualMW)} MW</b>
            </div>

            <div className="metricLine">
              <span>Mean Forecast Generation</span>
              <b>{fmt(met.meanForecastMW)} MW</b>
            </div>

            <div className="metricLine">
              <span>Unmatched Target Intervals</span>
              <b>
                {(counts.unmatchedActuals || 0) + (counts.unmatchedForecasts || 0) === 0 ? (
                  <span style={{ color: '#67e8c2' }}>0 (100% Verified)</span>
                ) : (
                  <span style={{ color: '#ffbd88' }}>
                    {counts.unmatchedActuals} act / {counts.unmatchedForecasts} fc
                  </span>
                )}
              </b>
            </div>
          </section>
        </div>

        {/* Largest Forecast Errors Audit Table */}
        <section className="panel">
          <div className="panelHead">
            <div>
              <div className="eyebrow">04 / INTERVAL AUDIT</div>
              <h2>Largest Forecast Deviations</h2>
              <p>Top deviations ranked by absolute error with decision cutoff timestamps.</p>
            </div>

            <div className="pills">
              <button
                className={`pill ${errorFilter === 'all' ? 'active' : ''}`}
                onClick={() => setErrorFilter('all')}
              >
                All Deviations
              </button>
              <button
                className={`pill ${errorFilter === 'over' ? 'active' : ''}`}
                onClick={() => setErrorFilter('over')}
              >
                Over-Forecasts (F &gt; A)
              </button>
              <button
                className={`pill ${errorFilter === 'under' ? 'active' : ''}`}
                onClick={() => setErrorFilter('under')}
              >
                Under-Forecasts (F &lt; A)
              </button>
            </div>
          </div>

          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Target Delivery Interval</th>
                  <th>Forecast Published</th>
                  <th>Forecast (MW)</th>
                  <th>Actual (MW)</th>
                  <th>Error (Δ MW)</th>
                  <th>Absolute Error</th>
                  <th>% Error</th>
                </tr>
              </thead>
              <tbody>
                {filteredErrors.map((x) => (
                  <tr key={x.startTime}>
                    <td>
                      {new Date(x.startTime).toLocaleDateString('en-GB', {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric',
                      })}{' '}
                      <b>
                        {new Date(x.startTime).toLocaleTimeString('en-GB', {
                          hour: '2-digit',
                          minute: '2-digit',
                          timeZone: 'UTC',
                        })}{' '}
                        UTC
                      </b>
                    </td>
                    <td style={{ color: '#8fa2b9' }}>
                      {x.publishTime
                        ? `${new Date(x.publishTime).toLocaleDateString('en-GB', {
                            day: '2-digit',
                            month: 'short',
                          })} ${new Date(x.publishTime).toLocaleTimeString('en-GB', {
                            hour: '2-digit',
                            minute: '2-digit',
                            timeZone: 'UTC',
                          })} UTC`
                        : '—'}
                    </td>
                    <td>{fmt(x.forecast)}</td>
                    <td>{fmt(x.actual)}</td>
                    <td className={x.error > 0 ? 'positive' : x.error < 0 ? 'negative' : ''}>
                      {x.error > 0 ? '+' : ''}
                      {fmt(x.error)}
                    </td>
                    <td>
                      <b>{fmt(x.absoluteError)}</b>
                    </td>
                    <td>{x.percentageError != null ? `${fmt(x.percentageError)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!filteredErrors.length && <Empty busy={busy} error={error} />}
          </div>
        </section>

        <footer>
          <span>WINDWORKS FORECAST INTELLIGENCE · REint FULL STACK SWE CHALLENGE v4</span>
          <span>
            Verified against official Elexon BMRS datasets (FUELHH &amp; WINDFOR). No missing data treated as zero.
          </span>
        </footer>
      </main>
    </div>
  );
}

function Metric({ label, value, unit, note, icon }) {
  return (
    <div className="kpi">
      <div className="kpiTop">
        <span>{label}</span>
        <i>{icon}</i>
      </div>
      <div className="kpiValue">
        {value}
        <small>{unit}</small>
      </div>
      <div className="kpiNote">{note}</div>
    </div>
  );
}

function Empty({ busy, error }) {
  return (
    <div className="empty">
      {busy
        ? 'Fetching source datasets from Elexon...'
        : error
        ? 'Could not load data. Check backend logs and network connection.'
        : 'No records matching the selected parameters.'}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
