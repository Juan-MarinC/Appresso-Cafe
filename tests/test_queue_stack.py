import unittest

from appresso_food.nucleo.queue_stack import PendingOrdersQueue, UndoAction, UndoStack


class PendingOrdersQueueTest(unittest.TestCase):
    def test_fifo_order(self):
        queue = PendingOrdersQueue()
        queue.enqueue(1)
        queue.enqueue(2)
        queue.enqueue(3)

        self.assertEqual(queue.dequeue(), 1)
        self.assertEqual(queue.dequeue(), 2)
        self.assertEqual(len(queue), 1)

    def test_remove_from_middle(self):
        queue = PendingOrdersQueue()
        queue.enqueue(1)
        queue.enqueue(2)
        queue.enqueue(3)
        queue.remove(2)

        self.assertEqual(queue.as_list(), [1, 3])


class UndoStackTest(unittest.TestCase):
    def test_lifo_order(self):
        stack = UndoStack()
        stack.push(UndoAction(kind="crear_pedido", order_id=1))
        stack.push(UndoAction(kind="crear_pedido", order_id=2))

        last = stack.pop()
        self.assertEqual(last.order_id, 2)
        self.assertEqual(stack.pop().order_id, 1)
        self.assertIsNone(stack.pop())

    def test_max_size_drops_oldest(self):
        stack = UndoStack(max_size=2)
        stack.push(UndoAction(kind="crear_pedido", order_id=1))
        stack.push(UndoAction(kind="crear_pedido", order_id=2))
        stack.push(UndoAction(kind="crear_pedido", order_id=3))

        self.assertEqual(len(stack), 2)
        self.assertEqual([a.order_id for a in stack.as_list()], [3, 2])


if __name__ == "__main__":
    unittest.main()
