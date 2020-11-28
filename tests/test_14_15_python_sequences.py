import pyuvm_unittest
from pyuvm import *
from threading import Thread
import time


class py1415_sequence_TestCase(pyuvm_unittest.pyuvm_TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.result_list = []

    @staticmethod
    def putter(put_method, data):
        for datum in data:
            put_method(datum)

    def getter(self, get_method, done_method=None):
        datum = 'empty'
        while True:
            datum = get_method()
            if datum.get_name() == 'end':
                break
            if done_method:
                done_method()
            self.result_list.append(datum)

    def response_getter(self, get_response_method, txn_id_list):
        for txn_id in txn_id_list:
            datum = get_response_method(txn_id)
            self.result_list.append(datum)
        pass

    class ItemClass(uvm_sequence_item):
        def __init__(self, name="seq_item", txn_id=0):
            super().__init__(name)
            self.transaction_id = txn_id
            self.condition = Condition()

        def __str__(self):
            return str(self.transaction_id)

    def run_put_get(self, put_method, get_method, done_method=None):
        get_thread = Thread(target=self.getter, args=(get_method, done_method), name="getter")
        get_thread.start()
        send_list = [self.ItemClass("5"), self.ItemClass("3"), self.ItemClass('two')]
        self.putter(put_method, send_list + [self.ItemClass('end')])
        time.sleep(.05)
        get_thread.join()
        self.assertEqual(send_list, self.result_list)

    def run_get_response(self, put_method, get_response_method):
        send_list = []
        for ii in range(5):
            send_list.append(self.ItemClass(txn_id=ii))
        get_thread = Thread(target=self.response_getter, args=(get_response_method, [4, 2]), name="run_get_response")
        get_thread.start()
        self.putter(put_method, send_list)
        get_thread.join()
        result = [xx.transaction_id for xx in self.result_list]
        self.assertEqual([4, 2], result)
        self.result_list = []
        get_thread2 = Thread(target=self.response_getter, args=(get_response_method, [5]), name="run_get_response_2")
        get_thread2.start()
        self.putter(put_method, [self.ItemClass(txn_id=10), self.ItemClass(txn_id=11)])
        time.sleep(0.01)
        alive = get_thread2.is_alive()
        self.assertTrue(alive)
        self.putter(put_method, [self.ItemClass(txn_id=5)])
        time.sleep(0.01)
        alive = get_thread2.is_alive()
        self.assertFalse(alive)
        get_thread.join()
        self.assertTrue(5, self.result_list[0].transaction_id)

    def test_ResponseQueue_put_get(self):
        rq = ResponseQueue()
        self.run_put_get(rq.put, rq.get)

    def test_ResponseQueue_get_response(self):
        rq = ResponseQueue()
        self.run_get_response(rq.put, rq.get_response)

    def test_uvm_item_export_check(self):
        sip = uvm_seq_item_port("sip", None)
        bpe = uvm_blocking_put_export("bpe", None)
        with self.assertRaises(error_classes.UVMTLMConnectionError):
            sip.connect(bpe)

    def test_uvm_item_port_put_get(self):
        sip = uvm_seq_item_port("sip", None)
        sie = uvm_seq_item_export("sie", None)
        sip.connect(sie)
        self.run_get_response(sip.put, sip.get_response)

    def test_uvm_item_port_put_req_get_next_item(self):
        sip = uvm_seq_item_port("sip", None)
        sie = uvm_seq_item_export("sie", None)
        sip.connect(sie)
        self.run_put_get(sip.put_req, sip.get_next_item, sip.item_done)

    def test_too_much_get_item(self):
        sip = uvm_seq_item_port("sip", None)
        sie = uvm_seq_item_export("sie", None)
        sip.connect(sie)
        sip.put_req(self.ItemClass(txn_id=0))
        sip.put_req(self.ItemClass(txn_id=1))
        sip.get_next_item()
        with self.assertRaises(error_classes.UVMSequenceError):
            sip.get_next_item()

    def test_premature_item_done(self):
        sip = uvm_seq_item_port("sip", None)
        sie = uvm_seq_item_export("sie", None)
        sip.connect(sie)
        with self.assertRaises(error_classes.UVMSequenceError):
            sip.item_done()

    @staticmethod
    def waiter(condition):
        with condition:
            condition.wait()

    def test_double_item_done(self):
        sip = uvm_seq_item_port("sip", None)
        sie = uvm_seq_item_export("sie", None)
        sip.connect(sie)
        sip.put_req(self.ItemClass(txn_id=0))
        sip.put_req(self.ItemClass(txn_id=1))
        item = sip.get_next_item()
        thread = Thread(target=self.waiter, args=(item.condition,), name="double_item_done")
        thread.start()
        sip.item_done()
        with self.assertRaises(error_classes.UVMSequenceError):
            sip.item_done()
        with item.condition:
            item.condition.notify_all()

    def test_item_done(self):
        sip = uvm_seq_item_port("sip", None)
        sie = uvm_seq_item_export("sie", None)
        sip.connect(sie)
        req = uvm_sequence_item("req")
        rsp = uvm_sequence_item("rsp")
        # There are three threads that test item_done
        # start_item: The thread that is waiting for start_item
        # finish_item: The thread that is waiting for finish_item
        # get_response: the thread that is waiting for get_response
        start_item_thread = Thread(target=self.waiter, args=(req.start_condition,), name="start_item")
        finish_item_thread = Thread(target=self.waiter, args=(req.finish_condition,), name="finish_item")
        rsp_thread = Thread(target=self.response_getter, args=(sip.get_response, [None]), name="rsp")

        start_item_thread.start()
        finish_item_thread.start()
        rsp_thread.start()
        time.sleep(.01)
        sip.put_req(req)
        req_back = sip.get_next_item()
        time.sleep(.01)
        # testing start_item
        self.assertEqual(req, req_back)
        self.assertFalse(start_item_thread.is_alive())
        self.assertTrue(finish_item_thread.is_alive())
        self.assertTrue(rsp_thread.is_alive())
        # testing item_done
        # Should finish the finish_item thread and the rsp thread.
        sip.item_done(rsp)
        time.sleep(.01)
        self.assertEqual(rsp, self.result_list[0])
        self.assertFalse(start_item_thread.is_alive())
        self.assertFalse(finish_item_thread.is_alive())
        self.assertFalse(rsp_thread.is_alive())
        start_item_thread.join()
        finish_item_thread.join()
        rsp_thread.join()

    def test_uvm_sequencer_put_get_response(self):
        seqr = uvm_sequencer("seqr", None)
        sip = uvm_seq_item_port("sip", None)
        sip.connect(seqr.seq_item_export)
        self.run_get_response(sip.put, seqr.get_response)

    def test_uvm_sequencer_put_req_get_next_item(self):
        seqr = uvm_sequencer("seqr", None)
        sip = uvm_seq_item_port("sip", None)
        sip.connect(seqr.seq_item_export)
        self.run_put_get(sip.put_req, seqr.get_next_item, sip.item_done)

    def test_seqr_item_done(self):
        seqr = uvm_sequencer("seqr", None)
        sip = uvm_seq_item_port("sip", None)
        sip.connect(seqr.seq_item_export)
        req = uvm_sequence_item("req")
        rsp = uvm_sequence_item("rsp")
        # There are three threads that test item_done
        # start_item: The thread that is waiting for start_item
        # finish_item: The thread that is waiting for finish_item
        # get_response: the thread that is waiting for get_response
        start_item_thread = Thread(target=self.waiter, args=(req.start_condition,), name="start_item")
        finish_item_thread = Thread(target=self.waiter, args=(req.finish_condition,), name="finish_item")
        rsp_thread = Thread(target=self.response_getter, args=(sip.get_response, [None]), name="rsp")

        start_item_thread.start()
        finish_item_thread.start()
        rsp_thread.start()
        time.sleep(.01)
        sip.put_req(req)
        req_back = sip.get_next_item()
        time.sleep(.01)
        # testing start_item
        self.assertEqual(req, req_back)
        self.assertFalse(start_item_thread.is_alive())
        self.assertTrue(finish_item_thread.is_alive())
        self.assertTrue(rsp_thread.is_alive())
        # testing item_done
        # Should finish the finish_item thread and the rsp thread.
        sip.item_done(rsp)
        time.sleep(.01)
        self.assertEqual(rsp, self.result_list[0])
        self.assertFalse(start_item_thread.is_alive())
        self.assertFalse(finish_item_thread.is_alive())
        self.assertFalse(rsp_thread.is_alive())
        start_item_thread.join()
        finish_item_thread.join()
        rsp_thread.join()

    # Time to test the sequence itself.
    def test_base_virtual_sequence(self):
        class basic_seq(uvm_sequence):
            def __init__(self, name, result_list):
                super().__init__(name)
                self.rl = result_list

            def body(self):
                self.rl.append('body')

        seq = basic_seq("basic_seq", self.result_list)
        seq.start()
        self.assertEqual('body', self.result_list[0])

    class timeout_sequencer(uvm_sequencer):
        def __init__(self, name, parent):
            super().__init__(name, parent)
            self.running = True

        def run_phase(self):
            while self.running:
                try:
                    next_item = self.seq_q.get(block=False)
                    with next_item.start_condition:
                        next_item.start_condition.notify_all()
                except Empty:
                    time.sleep(0.05)

    def seq_item_port_getter(self, sip=None):
        datum = sip.get_next_item()
        self.result_list.append(datum)

    def test_simple_get_item(self):
        class seq(uvm_sequence):
            def body(self):
                txn = uvm_sequence_item("txn")
                self.start_item(txn)
                txn.datum = 55
                self.finish_item(txn)

        seqr = self.timeout_sequencer("seqr", None)
        run_thread = Thread(target=seqr.run_phase, name="seqr.run_phase")
        run_thread.start()
        sip = uvm_seq_item_port("sip", None)
        sip.connect(seqr.seq_item_export)
        ss = seq("ss")
        start_thread = threading.Thread(target=ss.start, args=(seqr,), name="start_thread")
        start_thread.start()
        time.sleep(.1)
        item = sip.get_next_item()
        sip.item_done()
        seqr.running = False
        time.sleep(.1)
        self.assertEqual(55, item.datum)
        pass