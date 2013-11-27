# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Addons modules by CLEARCORP S.A.
#    Copyright (C) 2009-TODAY CLEARCORP S.A. (<http://clearcorp.co.cr>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp.osv import fields, osv, orm

class accountMove(orm.Model):
    _inherit = "account.move"
    
    OPTIONS = [
        ('void', 'Voids budget move'),
        ('budget', 'Budget move'),
    ]
    
    _columns = {
        'budget_move_line_ids':  fields.one2many('budget.move.line', 'account_move_id', 'Budget move lines'),
        'budget_type': fields.selection(OPTIONS, 'budget_type', readonly=True),
    }
    
    def post(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        invoice = context.get('invoice', False)
        valid_moves = self.validate(cr, uid, ids, context)

        if not valid_moves:
            raise osv.except_osv(_('Error!'), _('You cannot validate a non-balanced entry.\nMake sure you have configured payment terms properly.\nThe latest payment term line should be of the "Balance" type.'))

        obj_sequence = self.pool.get('ir.sequence')
        
        #=============================================================================#
        check_lines = []
        next_step = False
        amount = 0.0
        percentage = 0.0
        obj_move_line = self.pool.get('account.move.line')
        
        #Check if this account.move has distributions lines and check (only in valid_moves -> is a account.move object)
        for move in self.browse(cr, uid, valid_moves, context=context):
            move_lines = obj_move_line.search(cr, uid, [('move_id','=',move.id)])
            
            for line in obj_move_line.browse(cr, uid, move_lines):
                if line.account_id.moves_cash:
                     check_lines.append(line)
        
            #Check amount in line.distribution (if there exist any line.id)
            if len(check_lines) > 0:
                for line in check_lines: 
                    distribution_lines = self.pool.get('account.move.line.distribution').search(cr, uid, [('account_move_line_id', '=', line.id)])
                    
                    if len(distribution_lines) > 0:
                        #Sum distribution_amount. This amount is equal to line.amount (debit or credit).
                        for distribution in self.pool.get('account.move.line.distribution').browse(cr, uid, distribution_lines):
                            amount += distribution.distribution_amount
                            percentage += distribution.distribution_percentage
                        
                        #Find amount (debit or credit) and compare. 
                        if line.debit > 0:
                            amount_check = line.debit
                        else:
                            amount_check = line.credit
                        
                        #Continue with normal process
                        if (amount_check == amount) and (percentage == 100):                        
                            next_step = True
                            
                        else:
                            next_step = False
                            return {'value': {'account_move_line_id': line.id},
                                    'warning':{'title':'Warning','message':'Distribution amount for this move line does not match with original amount line'}}
    
                    #Continue with normal process
                    else:
                        next_step = True
            
            else:
                next_step = True
            
            #=============================================================================#
            if next_step:
                for move in self.browse(cr, uid, valid_moves, context=context):
                    if move.name =='/':
                        new_name = False
                        journal = move.journal_id
        
                        if invoice and invoice.internal_number:
                            new_name = invoice.internal_number
                        else:
                            if journal.sequence_id:
                                c = {'fiscalyear_id': move.period_id.fiscalyear_id.id}
                                new_name = obj_sequence.next_by_id(cr, uid, journal.sequence_id.id, c)
                            else:
                                raise osv.except_osv(_('Error!'), _('Please define a sequence on the journal.'))
                        
                        if new_name:
                            self.write(cr, uid, [move.id], {'name':new_name})
        
                cr.execute('UPDATE account_move '\
                           'SET state=%s '\
                           'WHERE id IN %s',
                           ('posted', tuple(valid_moves),))
        return True


class AccountMoveLine(osv.Model):
    _inherit = 'account.move.line'
    
    #===========================================================================
    # 
    # distribution_percentage_sum compute the percentage for the account.move.line.
    # Check the account.move.line.distribution and sum where id is the same for
    # account.move.line.
    # 
    # distribution_amount_sum compute the amount for the account.move.line.
    # Check the account.move.line.distribution and sum where id is the same for
    # account.move.line.
    # 
    #_account_move_lines_mod method return the account.move.line id's where the
    # store apply the change. This method is necessary to create a store. This
    # help to compute in a "automatic way" those fields (percentage and sum) and
    # is more easy to get this values from those fields. 
    #
    #===========================================================================
    
    def _sum_distribution_per(self, cr, uid, ids, field_name, args, context=None):
        res = {}       
        query = 'SELECT amld.id, SUM(amld.distribution_percentage) AS dis_per FROM '\
        'account_move_line_distribution amld '\
        'WHERE amld.id =  %s GROUP BY amld.id' % tuple(ids)
        cr.execute(query)
        for row in cr.dictfetchall():
            res[row['id']] = row['dis_per']        
        return res
    
    def _sum_distribution_amount(self, cr, uid, ids, field_name, args, context=None):
        res = {}       
        query = 'SELECT amld.id, SUM(amld.distribution_amount) AS dis_amount FROM '\
        'account_move_line_distribution amld '\
        'WHERE amld.id =  %s GROUP BY amld.id' % tuple(ids)
        cr.execute(query)
        for row in cr.dictfetchall():
            res[row['id']] = row['dis_amount']        
        return res
           
    def _account_move_lines_mod(self, cr, uid, amld_ids, context=None):
        list = []
        amld_obj = self.pool.get('account.move.line.distribution')
        
        for line in amld_obj.browse(cr, uid, amld_ids, context=context):
            list.append(line.account_move_line_id.id)
        return list
    
    _columns = {
        #=======Budget Move Line
        'budget_move_lines': fields.one2many('budget.move.line','move_line_id', 'Budget Move Lines'),
        
        #=======Percentage y amount distribution
        'distribution_percentage_sum': fields.function(_sum_distribution_per, type="float", method=True, string="Distributed percentage",
                                                   store={'account.move.line.distribution': (_account_move_lines_mod, ['distribution_percentage'], 10)}),        
        'distribution_amount_sum': fields.function(_sum_distribution_amount, type="float", method=True, string="Distributed amount",
                                                   store={'account.move.line.distribution': (_account_move_lines_mod, ['distribution_amount'], 10)}),        
        
        #=======account move line distributions
        'account_move_line_dist': fields.one2many('account.move.line.distribution','account_move_line_id', 'Account Move Line Distributions'),
        'type_distribution':fields.related('account_move_line_dist','type', type="selection", relation="account.move.line.distribution", string="Distribution type")
    }
    
    _defaults = {
        'distribution_percentage_sum': 0.0, 
        'distribution_amount_sum': 0.0,
    }
    
    