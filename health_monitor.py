"""
MEXC Pump Monitor - Health Monitor
Мониторинг здоровья системы и всех компонентов
"""

import asyncio
import logging
import time
import os
import sys
import psutil
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Статусы здоровья"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Здоровье компонента"""
    name: str
    status: HealthStatus
    last_check: int
    message: str = ""
    latency_ms: float = 0
    error_count: int = 0
    uptime_seconds: int = 0


@dataclass
class SystemMetrics:
    """Системные метрики"""
    timestamp: int
    
    # CPU
    cpu_percent: float = 0
    cpu_count: int = 0
    
    # Memory
    memory_total_mb: float = 0
    memory_used_mb: float = 0
    memory_percent: float = 0
    
    # Process
    process_memory_mb: float = 0
    process_cpu_percent: float = 0
    process_threads: int = 0
    
    # Network (estimated)
    connections_count: int = 0
    
    # Python specific
    python_version: str = ""
    asyncio_tasks: int = 0


@dataclass
class HealthReport:
    """Полный отчёт о здоровье"""
    timestamp: int
    overall_status: HealthStatus
    
    # Components
    components: List[ComponentHealth] = field(default_factory=list)
    
    # System metrics
    system: SystemMetrics = None
    
    # Alerts
    active_alerts: List[str] = field(default_factory=list)
    
    # Uptime
    uptime_seconds: int = 0
    start_time: int = 0


class HealthMonitor:
    """
    🏥 Health Monitor
    
    Мониторит:
    - Статус всех компонентов (API, WebSocket, Telegram, etc.)
    - Системные ресурсы (CPU, RAM, сеть)
    - Latency и ошибки
    - Uptime и availability
    
    Генерирует:
    - Алерты при проблемах
    - Периодические отчёты
    """
    
    # Thresholds
    CPU_WARNING_PCT = 80
    MEMORY_WARNING_PCT = 85
    ERROR_RATE_WARNING = 10  # errors per minute
    LATENCY_WARNING_MS = 5000
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Components to monitor
        self.components: Dict[str, ComponentHealth] = {}
        
        # Health checks (functions that return True/False)
        self._health_checks: Dict[str, Callable] = {}
        
        # Error tracking
        self.error_counts: Dict[str, List[int]] = {}  # component -> [timestamps]
        
        # Start time
        self.start_time = int(time.time() * 1000)
        
        # Metrics history
        self.metrics_history: List[SystemMetrics] = []
        self.max_metrics = 1000
        
        # Alerts
        self.active_alerts: List[str] = []
        self.alert_history: List[dict] = []
        self.max_alerts = 200
        
        # Stats
        self.stats = {
            'checks_performed': 0,
            'alerts_sent': 0,
            'components_registered': 0
        }
        
        self._running = False
        self._last_report_time = 0
        self._report_interval = 28800  # Every 8 hours
        self._last_alert_time: Dict[str, float] = {}  # Cooldown per alert type
        self._alert_cooldown = 1800  # 30 minutes cooldown
    
    async def start(self):
        """Запустить монитор"""
        self._running = True
        
        # Register default checks
        self._register_default_checks()
        
        # Start monitoring loop
        asyncio.create_task(self._monitor_loop())
        asyncio.create_task(self._periodic_report())
        
        logger.info("🏥 Health Monitor started")
    
    async def stop(self):
        """Остановить монитор"""
        self._running = False
    
    def _register_default_checks(self):
        """Зарегистрировать стандартные проверки"""
        # System check
        self.register_component('system', self._check_system)
        
        # Memory check
        self.register_component('memory', self._check_memory)
        
        # Event loop check
        self.register_component('event_loop', self._check_event_loop)
    
    def register_component(
        self,
        name: str,
        health_check: Callable = None,
        initial_status: HealthStatus = HealthStatus.UNKNOWN
    ):
        """
        Зарегистрировать компонент для мониторинга
        
        Args:
            name: Имя компонента
            health_check: Функция проверки (async или sync, returns bool)
            initial_status: Начальный статус
        """
        self.components[name] = ComponentHealth(
            name=name,
            status=initial_status,
            last_check=int(time.time() * 1000)
        )
        
        if health_check:
            self._health_checks[name] = health_check
        
        self.error_counts[name] = []
        self.stats['components_registered'] = len(self.components)
        
        logger.debug(f"Registered component: {name}")
    
    def update_component(
        self,
        name: str,
        status: HealthStatus,
        message: str = "",
        latency_ms: float = 0
    ):
        """Обновить статус компонента вручную"""
        if name not in self.components:
            self.register_component(name)
        
        comp = self.components[name]
        old_status = comp.status
        
        comp.status = status
        comp.message = message
        comp.latency_ms = latency_ms
        comp.last_check = int(time.time() * 1000)
        
        if status == HealthStatus.UNHEALTHY:
            self.error_counts[name].append(int(time.time()))
            # Keep only last 5 minutes
            cutoff = int(time.time()) - 300
            self.error_counts[name] = [t for t in self.error_counts[name] if t > cutoff]
            comp.error_count = len(self.error_counts[name])
        
        # Alert on status change
        if old_status == HealthStatus.HEALTHY and status == HealthStatus.UNHEALTHY:
            asyncio.create_task(self._alert(f"🔴 {name} is UNHEALTHY: {message}"))
        elif old_status == HealthStatus.UNHEALTHY and status == HealthStatus.HEALTHY:
            asyncio.create_task(self._alert(f"🟢 {name} recovered"))
    
    def record_error(self, component: str, error: str = None):
        """Записать ошибку компонента"""
        if component not in self.error_counts:
            self.error_counts[component] = []
        
        self.error_counts[component].append(int(time.time()))
        
        # Keep only last 5 minutes
        cutoff = int(time.time()) - 300
        self.error_counts[component] = [t for t in self.error_counts[component] if t > cutoff]
        
        if component in self.components:
            self.components[component].error_count = len(self.error_counts[component])
            
            # Too many errors = degraded
            if len(self.error_counts[component]) >= self.ERROR_RATE_WARNING:
                self.components[component].status = HealthStatus.DEGRADED
    
    async def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self._running:
            try:
                # Run all health checks
                await self._run_health_checks()
                
                # Collect system metrics
                metrics = self._collect_system_metrics()
                self.metrics_history.append(metrics)
                if len(self.metrics_history) > self.max_metrics:
                    self.metrics_history = self.metrics_history[-self.max_metrics:]
                
                # Check for system issues
                await self._check_system_thresholds(metrics)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(10)
    
    async def _run_health_checks(self):
        """Выполнить все проверки здоровья"""
        for name, check_func in self._health_checks.items():
            try:
                start = time.time()
                
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                
                latency = (time.time() - start) * 1000
                
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                self.update_component(name, status, latency_ms=latency)
                
                self.stats['checks_performed'] += 1
                
            except Exception as e:
                self.update_component(
                    name,
                    HealthStatus.UNHEALTHY,
                    message=str(e)
                )
    
    def _collect_system_metrics(self) -> SystemMetrics:
        """Собрать системные метрики"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            
            # Memory
            memory = psutil.virtual_memory()
            
            # Process
            process = psutil.Process()
            process_memory = process.memory_info().rss / (1024 * 1024)
            process_cpu = process.cpu_percent()
            process_threads = process.num_threads()
            
            # Connections
            try:
                connections = len(process.connections())
            except:
                connections = 0
            
            # Asyncio tasks
            try:
                loop = asyncio.get_running_loop()
                tasks = len(asyncio.all_tasks(loop))
            except:
                tasks = 0
            
            return SystemMetrics(
                timestamp=int(time.time() * 1000),
                cpu_percent=cpu_percent,
                cpu_count=cpu_count,
                memory_total_mb=memory.total / (1024 * 1024),
                memory_used_mb=memory.used / (1024 * 1024),
                memory_percent=memory.percent,
                process_memory_mb=process_memory,
                process_cpu_percent=process_cpu,
                process_threads=process_threads,
                connections_count=connections,
                python_version=sys.version.split()[0],
                asyncio_tasks=tasks
            )
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            return SystemMetrics(timestamp=int(time.time() * 1000))
    
    async def _check_system_thresholds(self, metrics: SystemMetrics):
        """Проверить пороговые значения"""
        now = time.time()
        
        # Check CPU with cooldown
        if metrics.cpu_percent > self.CPU_WARNING_PCT:
            if now - self._last_alert_time.get('cpu', 0) > self._alert_cooldown:
                await self._alert(f"⚠️ High CPU: {metrics.cpu_percent:.1f}%")
                self._last_alert_time['cpu'] = now
        
        # Check Memory with cooldown
        if metrics.memory_percent > self.MEMORY_WARNING_PCT:
            if now - self._last_alert_time.get('memory', 0) > self._alert_cooldown:
                await self._alert(f"⚠️ High Memory: {metrics.memory_percent:.1f}%")
                self._last_alert_time['memory'] = now
    
    async def _alert(self, message: str):
        """Отправить алерт"""
        self.alert_history.append({
            'timestamp': int(time.time() * 1000),
            'message': message
        })
        
        if len(self.alert_history) > self.max_alerts:
            self.alert_history = self.alert_history[-self.max_alerts:]
        
        self.stats['alerts_sent'] += 1
        
        logger.warning(f"Health Alert: {message}")
        
        if self.telegram:
            try:
                await self.telegram.send_message(f"🏥 <b>HEALTH ALERT</b>\n{message}")
            except:
                pass
    
    async def _periodic_report(self):
        """Периодические отчёты о здоровье (только в лог, без Telegram)"""
        while self._running:
            try:
                await asyncio.sleep(self._report_interval)
                
                report = self.get_health_report()
                # Log locally only — use /health command for on-demand reports
                logger.info(f"HEALTH: {report.overall_status.value} | Uptime: {timedelta(seconds=report.uptime_seconds)}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic report error: {e}")
    
    # Default health check functions
    def _check_system(self) -> bool:
        """Проверка системы"""
        return True
    
    def _check_memory(self) -> bool:
        """Проверка памяти"""
        try:
            memory = psutil.virtual_memory()
            return memory.percent < 95
        except:
            return True
    
    def _check_event_loop(self) -> bool:
        """Проверка event loop"""
        try:
            loop = asyncio.get_running_loop()
            return loop.is_running()
        except:
            return False
    
    def get_health_report(self) -> HealthReport:
        """Получить полный отчёт о здоровье"""
        now = int(time.time() * 1000)
        uptime = (now - self.start_time) // 1000
        
        # Determine overall status
        statuses = [comp.status for comp in self.components.values()]
        
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN
        
        # Get latest metrics
        system = self.metrics_history[-1] if self.metrics_history else None
        
        return HealthReport(
            timestamp=now,
            overall_status=overall,
            components=list(self.components.values()),
            system=system,
            active_alerts=self.active_alerts.copy(),
            uptime_seconds=uptime,
            start_time=self.start_time
        )
    
    def format_report(self, report: HealthReport) -> str:
        """Форматировать отчёт для Telegram"""
        status_emoji = {
            HealthStatus.HEALTHY: "🟢",
            HealthStatus.DEGRADED: "🟡",
            HealthStatus.UNHEALTHY: "🔴",
            HealthStatus.UNKNOWN: "⚪"
        }
        
        uptime_str = str(timedelta(seconds=report.uptime_seconds))
        
        components_str = ""
        for comp in report.components[:10]:  # Max 10 components
            emoji = status_emoji.get(comp.status, "⚪")
            components_str += f"\n{emoji} {comp.name}: {comp.status.value}"
        
        system_str = ""
        if report.system:
            system_str = f"""
💻 CPU: {report.system.cpu_percent:.1f}%
🧠 RAM: {report.system.memory_percent:.1f}%
📦 Process: {report.system.process_memory_mb:.0f}MB
🔄 Tasks: {report.system.asyncio_tasks}"""
        
        alerts_str = ""
        if report.active_alerts:
            alerts_str = "\n\n⚠️ <b>Active Alerts:</b>\n" + "\n".join(report.active_alerts[:5])
        
        return f"""
🏥 <b>HEALTH REPORT</b>

{status_emoji.get(report.overall_status, "⚪")} Overall: <b>{report.overall_status.value.upper()}</b>
⏱️ Uptime: {uptime_str}

📊 <b>Components:</b>{components_str}

📈 <b>System:</b>{system_str}
{alerts_str}
"""
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return {
            **self.stats,
            'uptime_seconds': (int(time.time() * 1000) - self.start_time) // 1000,
            'active_alerts': len(self.active_alerts),
            'metrics_collected': len(self.metrics_history)
        }

    def get_health_status(self) -> Dict:
        """
        🚀 Получить быстрый статус для Telegram
        Возвращает реальные проценты загрузки CPU и RAM
        """
        try:
            # CPU (one-shot measurement)
            cpu = psutil.cpu_percent(interval=0.1)
            
            # Memory
            mem = psutil.virtual_memory().percent
            
            # Uptime
            uptime_sec = (int(time.time() * 1000) - self.start_time) // 1000
            uptime_str = str(timedelta(seconds=uptime_sec))
            
            # Check components
            api_ok = True
            ws_ok = True
            
            for comp in self.components.values():
                if 'api' in comp.name.lower() and comp.status != HealthStatus.HEALTHY:
                    api_ok = False
                if 'ws' in comp.name.lower() and comp.status != HealthStatus.HEALTHY:
                    ws_ok = False
            
            return {
                'cpu': cpu,
                'memory': mem,
                'api_ok': api_ok,
                'ws_ok': ws_ok,
                'uptime': uptime_str,
                'status': 'Operational'
            }
        except Exception as e:
            logger.error(f"Error in get_health_status: {e}")
            return {
                'cpu': 0,
                'memory': 0,
                'api_ok': False,
                'ws_ok': False,
                'uptime': 'N/A',
                'status': 'Error'
            }
