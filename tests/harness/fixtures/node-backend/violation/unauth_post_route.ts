import express from 'express';
const router = express.Router();

router.post('/users', (req, res) => {
  res.status(201).json({ id: 'x' });
});
