import contextlib
import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from ops.run_strategy_acceptance import main


class AcceptanceControlTests(unittest.TestCase):
    def assert_rejected_before_model(self,args):
        with patch('ops.run_strategy_acceptance.CompatibleModelClient.from_env') as client:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):main(args)
            client.assert_not_called()

    def test_formal_real_requires_explicit_confirmation(self):
        self.assert_rejected_before_model(['--provider','compatible'])

    def test_small_limit_cannot_bypass_formal_confirmation(self):
        self.assert_rejected_before_model(['--provider','compatible','--limit','50'])

    def test_existing_report_is_not_overwritten_or_paid_for(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'existing.json'
            output.touch()
            self.assert_rejected_before_model(['--limit','1','--output',str(output)])
            self.assertEqual(output.read_text(),'')

    def test_small_offline_report_is_not_formal_acceptance(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            output=Path(directory)/'report.json'
            self.assertEqual(main(['--provider','offline','--limit','5','--output',str(output)]),0)
            import json
            report=json.loads(output.read_text(encoding='utf-8'))
            self.assertFalse(report['formal_acceptance_run'])
            self.assertIsNone(report['summary']['meets_structure_target'])
            self.assertFalse(report['summary']['first_stage_accepted'])
            self.assertEqual(report['human_review']['status'],'pending')
            self.assertEqual(report['config']['validation_version'],'strategy-rules-v8-delivery-quality')
            self.assertEqual(len(report['records']),5)
