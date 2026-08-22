"""
Run Backtest - Test all frameworks against historical data
Generates detailed performance reports
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from frameworks import FrameworkRegistry
from backtester.backtest import Backtester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_all_frameworks_backtest(backtester: Backtester, snapshot_date: datetime, 
                               stock_data: dict, end_date: datetime) -> dict:
    """
    Run all registered frameworks against the same data
    
    Returns:
        Dict with results for all frameworks
    """
    
    # Get all frameworks
    frameworks_dict = FrameworkRegistry.instantiate_all()
    
    if not frameworks_dict:
        logger.error("No frameworks found!")
        return {}
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Testing {len(frameworks_dict)} Frameworks")
    logger.info(f"Snapshot Date: {snapshot_date.date()}")
    logger.info(f"End Date: {end_date.date()}")
    logger.info(f"{'='*80}\n")
    
    all_results = {
        'test_date': datetime.now().isoformat(),
        'snapshot_date': snapshot_date.isoformat(),
        'end_date': end_date.isoformat(),
        'frameworks': {}
    }
    
    for framework_name, framework in frameworks_dict.items():
        logger.info(f"Testing: {framework.name}")
        logger.info(f"Description: {framework.description}")
        
        try:
            result = backtester.backtest_framework(
                framework=framework,
                snapshot_date=snapshot_date,
                stock_data=stock_data,
                end_date=end_date,
                top_n=5
            )
            
            all_results['frameworks'][framework_name] = result
            
            # Print results
            logger.info(f"  → Avg Return: {result['metrics']['average_return_percent']:.2f}%")
            logger.info(f"  → Win Rate: {result['metrics']['win_rate_percent']:.1f}%")
            logger.info(f"  → Best Pick: {result['metrics']['best_return_percent']:.2f}%\n")
            
        except Exception as e:
            logger.error(f"  ✗ Error: {str(e)}\n")
            all_results['frameworks'][framework_name] = {
                'error': str(e)
            }
    
    return all_results


def generate_comparison_report(results: dict) -> str:
    """Generate markdown comparison report"""
    
    report = "# NSE Framework Research Backtest Report\n\n"
    
    report += f"**Test Date:** {results['test_date']}\n"
    report += f"**Snapshot Date:** {results['snapshot_date']}\n"
    report += f"**End Date:** {results['end_date']}\n\n"
    
    # Performance table
    report += "## Framework Comparison\n\n"
    report += "| Framework | Avg Return % | Win Rate % | Best Return % | Trades |\n"
    report += "|-----------|-------------|-----------|--------------|--------|\n"
    
    for framework_name, framework_result in results['frameworks'].items():
        if 'error' in framework_result:
            report += f"| {framework_name} | ERROR | - | - | - |\n"
            continue
        
        metrics = framework_result['metrics']
        report += (
            f"| {framework_name} | "
            f"{metrics['average_return_percent']:.2f} | "
            f"{metrics['win_rate_percent']:.1f} | "
            f"{metrics['best_return_percent']:.2f} | "
            f"{metrics['successful_trades']} |\n"
        )
    
    report += "\n## Detailed Results\n\n"
    
    for framework_name, framework_result in results['frameworks'].items():
        if 'error' in framework_result:
            continue
        
        report += f"### {framework_name}\n"
        report += f"{framework_result['framework_description']}\n\n"
        
        report += "**Top 5 Picks:**\n"
        for pick in framework_result['picks']:
            report += f"- **{pick['symbol']}** (Score: {pick['score']})\n"
        
        report += "\n**Performance:**\n"
        for perf in framework_result['performance']:
            if perf['status'] == 'success':
                report += (
                    f"- {perf['symbol']}: "
                    f"{perf['returns_percent']:+.2f}% "
                    f"({perf['entry_price']:.2f} → {perf['exit_price']:.2f})\n"
                )
            else:
                report += f"- {perf['symbol']}: {perf['status']}\n"
        
        report += f"\n**Metrics:**\n"
        report += f"- Average Return: {framework_result['metrics']['average_return_percent']:.2f}%\n"
        report += f"- Win Rate: {framework_result['metrics']['win_rate_percent']:.1f}%\n"
        report += f"- Best/Worst: {framework_result['metrics']['best_return_percent']:.2f}% / "
        report += f"{framework_result['metrics']['worst_return_percent']:.2f}%\n\n"
    
    report += "## Methodology\n\n"
    report += "Different frameworks are tested on the same stock data at a point in time.\n"
    report += "Performance is measured from the snapshot date to the end date.\n"
    report += "This tests whether the ranking methodology would have selected good performers.\n\n"
    
    report += "## Limitations\n\n"
    report += "- Survivorship bias (only active stocks tested)\n"
    report += "- No transaction costs or slippage modeled\n"
    report += "- Historical performance ≠ future results\n"
    report += "- Limited to available API data\n"
    
    return report


def save_results(results: dict, report: str, data_dir: str = "framework_research/data") -> dict:
    """Save results and report to files"""
    
    results_dir = Path(data_dir) / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Save JSON results
    results_file = results_dir / f"backtest_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    logger.info(f"✓ Results saved: {results_file}")
    
    # Save markdown report
    report_file = results_dir / f"backtest_report_{timestamp}.md"
    with open(report_file, 'w') as f:
        f.write(report)
    logger.info(f"✓ Report saved: {report_file}")
    
    return {
        'results_file': str(results_file),
        'report_file': str(report_file)
    }


def main():
    """Main backtest runner"""
    
    data_dir = "framework_research/data"
    backtester = Backtester(data_dir)
    
    # Get available snapshots
    snapshots = backtester.list_snapshots()
    
    if not snapshots:
        logger.error("No snapshots found! Run capture_snapshot.py first.")
        return
    
    logger.info(f"Found {len(snapshots)} snapshots:")
    for snapshot in snapshots:
        logger.info(f"  - {snapshot}")
    
    # Use the first snapshot (earliest date)
    snapshot_file = snapshots[0]
    snapshot_data = backtester.load_snapshot(snapshot_file)
    
    if not snapshot_data or 'stocks' not in snapshot_data:
        logger.error(f"Invalid snapshot: {snapshot_file}")
        return
    
    # Extract date from snapshot
    snapshot_date_str = snapshot_file.split('_')[1].replace('.json', '')
    snapshot_date = datetime.strptime(snapshot_date_str, '%Y%m%d')
    
    # Use current date as end date (or 1 year from snapshot for historical testing)
    end_date = datetime.now()
    
    # Run all frameworks
    results = run_all_frameworks_backtest(
        backtester,
        snapshot_date,
        snapshot_data['stocks'],
        end_date
    )
    
    # Generate report
    report = generate_comparison_report(results)
    
    # Save results
    file_paths = save_results(results, report, data_dir)
    
    logger.info(f"\n{'='*80}")
    logger.info("✓ Backtest complete!")
    logger.info(f"{'='*80}")
    logger.info(f"Results: {file_paths['results_file']}")
    logger.info(f"Report:  {file_paths['report_file']}")
    
    # Print summary
    logger.info("\n" + report)


if __name__ == "__main__":
    main()
