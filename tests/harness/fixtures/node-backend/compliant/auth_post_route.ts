import express from 'express';
import { requireAuth, rateLimit } from './middleware';

const router = express.Router();

router.post('/users', requireAuth, rateLimit, (req, res) => {
  res.status(201).json({ id: 'x' });
});
