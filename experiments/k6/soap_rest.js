import http from 'k6/http';
import { check, fail, sleep } from 'k6';

const WORKLOAD = __ENV.WORKLOAD || 'tens';
const DURATION = __ENV.SCENARIO_DURATION || '20s';
const REST_URL = __ENV.REST_URL || 'http://rest-service:8000/v1/tasks';
const SOAP_URL = __ENV.SOAP_URL || 'http://soap-service:8001/';
const SEQUENTIAL_SCENARIOS = (__ENV.SEQUENTIAL_SCENARIOS || 'true').toLowerCase() !== 'false';
const SCENARIO_GAP_SECONDS = Number(__ENV.SCENARIO_GAP_SECONDS || '5');
const REQUEST_TIMEOUT = __ENV.REQUEST_TIMEOUT || '30s';
const STARTUP_RETRIES = Number(__ENV.STARTUP_RETRIES || '30');
const STARTUP_DELAY_SECONDS = Number(__ENV.STARTUP_DELAY_SECONDS || '2');

const INTERFACE_MAINTENANCE_POINTS = {
  REST: '13',
  SOAP: '15',
};

function scenario(exec, rate, duration, preAllocatedVUs, maxVUs, tags) {
  return {
    executor: 'constant-arrival-rate',
    exec,
    rate,
    timeUnit: '1s',
    duration,
    gracefulStop: '5s',
    preAllocatedVUs,
    maxVUs,
    tags: {
      ...tags,
      rate_per_second: String(rate),
      concurrency: String(preAllocatedVUs),
      workload: WORKLOAD,
    },
  };
}

function durationSeconds(duration) {
  const match = String(duration).match(/^(\d+(?:\.\d+)?)(ms|s|m|h)$/);
  if (!match) return 0;
  const value = Number(match[1]);
  const unit = match[2];
  if (unit === 'ms') return value / 1000;
  if (unit === 's') return value;
  if (unit === 'm') return value * 60;
  if (unit === 'h') return value * 3600;
  return 0;
}

function sequenced(entries) {
  if (!SEQUENTIAL_SCENARIOS) {
    return Object.fromEntries(entries);
  }
  let offset = 0;
  return Object.fromEntries(entries.map(([name, config]) => {
    const current = { ...config, startTime: `${Math.ceil(offset)}s` };
    offset += durationSeconds(config.duration) + SCENARIO_GAP_SECONDS;
    return [name, current];
  }));
}

function quickScenarios() {
  return sequenced([
    ['rest_low', scenario('restLow', 2, DURATION, 2, 8, { test_scenario: 'rest_low', protocol: 'REST' })],
    ['soap_low', scenario('soapLow', 2, DURATION, 2, 8, { test_scenario: 'soap_low', protocol: 'SOAP' })],
    ['rest_medium', scenario('restMedium', 8, DURATION, 8, 32, { test_scenario: 'rest_medium', protocol: 'REST' })],
    ['soap_medium', scenario('soapMedium', 8, DURATION, 8, 32, { test_scenario: 'soap_medium', protocol: 'SOAP' })],
    ['mixed_medium_rest', scenario('mixedRest', 4, DURATION, 4, 16, { test_scenario: 'mixed_medium', protocol: 'REST' })],
    ['mixed_medium_soap', scenario('mixedSoap', 4, DURATION, 4, 16, { test_scenario: 'mixed_medium', protocol: 'SOAP' })],
  ]);
}

function tensScenarios() {
  return sequenced([
    ['rest_10k', scenario('rest10k', 50, '200s', 32, 128, { test_scenario: 'rest_10k', protocol: 'REST', target_requests: '10000' })],
    ['soap_10k', scenario('soap10k', 50, '200s', 32, 128, { test_scenario: 'soap_10k', protocol: 'SOAP', target_requests: '10000' })],
    ['mixed_20k_rest', scenario('mixed20kRest', 25, '400s', 24, 96, { test_scenario: 'mixed_20k', protocol: 'REST', target_requests: '10000' })],
    ['mixed_20k_soap', scenario('mixed20kSoap', 25, '400s', 24, 96, { test_scenario: 'mixed_20k', protocol: 'SOAP', target_requests: '10000' })],
  ]);
}

function hundredsScenarios() {
  return sequenced([
    ['rest_100k', scenario('rest100k', 40, '2500s', 32, 128, { test_scenario: 'rest_100k', protocol: 'REST', target_requests: '100000' })],
    ['soap_100k', scenario('soap100k', 40, '2500s', 32, 128, { test_scenario: 'soap_100k', protocol: 'SOAP', target_requests: '100000' })],
    ['mixed_200k_rest', scenario('mixed200kRest', 20, '5000s', 24, 96, { test_scenario: 'mixed_200k', protocol: 'REST', target_requests: '100000' })],
    ['mixed_200k_soap', scenario('mixed200kSoap', 20, '5000s', 24, 96, { test_scenario: 'mixed_200k', protocol: 'SOAP', target_requests: '100000' })],
  ]);
}

function millionsScenarios() {
  return sequenced([
    ['rest_1m', scenario('rest1m', 60, '16667s', 32, 128, { test_scenario: 'rest_1m', protocol: 'REST', target_requests: '1000000' })],
    ['soap_1m', scenario('soap1m', 60, '16667s', 32, 128, { test_scenario: 'soap_1m', protocol: 'SOAP', target_requests: '1000000' })],
    ['mixed_2m_rest', scenario('mixed2mRest', 30, '33334s', 24, 96, { test_scenario: 'mixed_2m', protocol: 'REST', target_requests: '1000000' })],
    ['mixed_2m_soap', scenario('mixed2mSoap', 30, '33334s', 24, 96, { test_scenario: 'mixed_2m', protocol: 'SOAP', target_requests: '1000000' })],
  ]);
}

function selectedScenarios() {
  if (WORKLOAD === 'quick') return quickScenarios();
  if (WORKLOAD === 'tens') return tensScenarios();
  if (WORKLOAD === 'hundreds') return hundredsScenarios();
  if (WORKLOAD === 'millions') return millionsScenarios();
  if (WORKLOAD === 'all') return { ...quickScenarios(), ...tensScenarios(), ...hundredsScenarios(), ...millionsScenarios() };
  return tensScenarios();
}

export let options = {
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
  scenarios: selectedScenarios(),
};

function waitForEndpoint(name, url, predicate) {
  for (let attempt = 1; attempt <= STARTUP_RETRIES; attempt += 1) {
    const response = http.get(url, { timeout: REQUEST_TIMEOUT, tags: { setup_probe: name } });
    if (predicate(response)) {
      return;
    }
    sleep(STARTUP_DELAY_SECONDS);
  }
  fail(`Endpoint ${name} não ficou pronto: ${url}`);
}

export function setup() {
  waitForEndpoint('rest_health', REST_URL.replace(/\/v1\/tasks$/, '/health'), (response) => response.status === 200);
  waitForEndpoint('soap_wsdl', `${SOAP_URL}?wsdl`, (response) => response.status === 200 && response.body && response.body.includes('wsdl:definitions'));
}

function samplePayload() {
  return {
    title: `Tarefa k6 ${__VU}-${__ITER}`,
    description: 'Payload sintético do gerenciador de tarefas para comparar REST e SOAP.',
    status: ['pending', 'done', 'archived'][__ITER % 3],
    priority: ((__ITER % 5) + 1),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    sample_id: `${__VU}-${__ITER}`,
  };
}

function escapeXml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function soapEnvelope(payload) {
  const payloadJson = escapeXml(JSON.stringify(payload));
  return `<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="urn:grupo03.soap.tasks">
  <soapenv:Body>
    <tns:create_task>
      <tns:payload_json>${payloadJson}</tns:payload_json>
    </tns:create_task>
  </soapenv:Body>
</soapenv:Envelope>`;
}

function byteLength(value) {
  return unescape(encodeURIComponent(value)).length;
}

function submitRest() {
  const body = JSON.stringify(samplePayload());
  const response = http.post(REST_URL, body, {
    headers: { 'Content-Type': 'application/json' },
    timeout: REQUEST_TIMEOUT,
    tags: {
      endpoint: 'create_task',
      payload_body_bytes: String(byteLength(body)),
      interface_maintenance_points: INTERFACE_MAINTENANCE_POINTS.REST,
    },
  });
  check(response, {
    'REST status 201': (r) => r.status === 201,
  });
}

function submitSoap() {
  const body = soapEnvelope(samplePayload());
  const response = http.post(SOAP_URL, body, {
    headers: {
      'Content-Type': 'text/xml; charset=utf-8',
      SOAPAction: 'create_task',
    },
    timeout: REQUEST_TIMEOUT,
    tags: {
      endpoint: 'create_task',
      payload_body_bytes: String(byteLength(body)),
      interface_maintenance_points: INTERFACE_MAINTENANCE_POINTS.SOAP,
    },
  });
  check(response, {
    'SOAP status 200': (r) => r.status === 200,
    'SOAP created': (r) => r.body && r.body.includes('created'),
  });
}

export function restLow() {
  submitRest();
}

export default function () {
  submitRest();
}

export function restMedium() {
  submitRest();
}

export function soapLow() {
  submitSoap();
}

export function soapMedium() {
  submitSoap();
}

export function mixedRest() {
  submitRest();
}

export function mixedSoap() {
  submitSoap();
}

export function rest10k() {
  submitRest();
}

export function soap10k() {
  submitSoap();
}

export function mixed20kRest() {
  submitRest();
}

export function mixed20kSoap() {
  submitSoap();
}

export function rest100k() {
  submitRest();
}

export function soap100k() {
  submitSoap();
}

export function mixed200kRest() {
  submitRest();
}

export function mixed200kSoap() {
  submitSoap();
}

export function rest1m() {
  submitRest();
}

export function soap1m() {
  submitSoap();
}

export function mixed2mRest() {
  submitRest();
}

export function mixed2mSoap() {
  submitSoap();
}
